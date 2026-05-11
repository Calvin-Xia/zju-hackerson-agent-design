# Phase 3 遗留问题修复计划

> **For agentic workers:** 使用 subagent-driven-development 执行此计划

**Goal:** 修复 Phase 3 知识图谱模块的所有遗留问题，使其完全符合 spec 要求

**Architecture:** 后端 FastAPI + 前端 React/ECharts，修改集中在 src/api/routes/kg.py、src/kg/graph_store.py、frontend/src/components/KnowledgeGraphPanel.tsx

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, React 19, ECharts, TypeScript

---

## Task 1: 添加 PUT /api/kg/{file_id} 节点/关系更新接口

**Files:**
- Modify: `src/api/routes/kg.py`
- Modify: `src/kg/graph_store.py`

### Step 1: 在 graph_store.py 中添加 update_node 和 update_relation 方法

```python
def update_node(self, file_id: str, node_id: str, updates: dict) -> bool:
    """更新节点"""
    graph = self.load(file_id)
    if not graph:
        return False
    
    for node in graph.nodes:
        if node.id == node_id:
            for key, value in updates.items():
                if hasattr(node, key):
                    setattr(node, key, value)
            self.save(file_id, graph)
            return True
    return False

def update_relation(self, file_id: str, source: str, target: str, relation_type: str, updates: dict) -> bool:
    """更新关系"""
    graph = self.load(file_id)
    if not graph:
        return False
    
    for rel in graph.relations:
        if rel.source == source and rel.target == target and rel.relation_type == relation_type:
            for key, value in updates.items():
                if hasattr(rel, key):
                    setattr(rel, key, value)
            self.save(file_id, graph)
            return True
    return False
```

### Step 2: 在 kg.py 中添加 PUT 接口

```python
class NodeUpdateRequest(BaseModel):
    name: Optional[str] = None
    definition: Optional[str] = None
    category: Optional[str] = None

class RelationUpdateRequest(BaseModel):
    description: Optional[str] = None
    confidence: Optional[float] = None

@router.put("/graph/{file_id}/node/{node_id}")
async def update_node(file_id: str, node_id: str, request: NodeUpdateRequest):
    """更新节点"""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    success = graph_store.update_node(file_id, node_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found")
    
    return {"message": "Node updated successfully"}

@router.put("/graph/{file_id}/relation")
async def update_relation(file_id: str, source: str, target: str, relation_type: str, request: RelationUpdateRequest):
    """更新关系"""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    success = graph_store.update_relation(file_id, source, target, relation_type, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Relation not found")
    
    return {"message": "Relation updated successfully"}
```

### Step 3: 运行测试验证

Run: `python -m pytest tests/ -v`
Expected: 所有测试通过

---

## Task 2: 实现边点击交互（显示关系详情）

**Files:**
- Modify: `frontend/src/components/KnowledgeGraphPanel.tsx`

### Step 1: 添加关系详情状态和 Modal

```typescript
const [selectedRelation, setSelectedRelation] = useState<GraphLink | null>(null);
const [relationModalVisible, setRelationModalVisible] = useState(false);
```

### Step 2: 修改 handleNodeClick 处理边点击

```typescript
const handleChartClick = useCallback((params: any) => {
  if (params.dataType === 'node') {
    const node = graphData?.nodes.find(n => n.id === params.data.id);
    if (node) {
      setSelectedNode(node);
      setModalVisible(true);
    }
  } else if (params.dataType === 'edge') {
    const link = graphData?.links.find(l => 
      l.source === params.data.source && l.target === params.data.target
    );
    if (link) {
      setSelectedRelation(link);
      setRelationModalVisible(true);
    }
  }
}, [graphData]);
```

### Step 3: 添加关系详情 Modal

```tsx
<Modal
  title="关系详情"
  open={relationModalVisible}
  onCancel={() => setRelationModalVisible(false)}
  footer={null}
  width={400}
>
  {selectedRelation && (
    <div>
      <Paragraph>
        <Text strong>源节点: </Text>
        {selectedRelation.source}
      </Paragraph>
      <Paragraph>
        <Text strong>目标节点: </Text>
        {selectedRelation.target}
      </Paragraph>
      <Paragraph>
        <Text strong>关系类型: </Text>
        <Tag>{RELATION_LABELS[selectedRelation.relation_type] || selectedRelation.relation_type}</Tag>
      </Paragraph>
      <Paragraph>
        <Text strong>描述: </Text>
        {selectedRelation.description}
      </Paragraph>
    </div>
  )}
</Modal>
```

---

## Task 3: 实现教材来源颜色区分

**Files:**
- Modify: `frontend/src/components/KnowledgeGraphPanel.tsx`

### Step 1: 添加教材颜色映射

```typescript
const TEXTBOOK_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
  '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#48b8d0',
];

const getTextbookColor = (textbookId: string, textbookIds: string[]): string => {
  const index = textbookIds.indexOf(textbookId);
  return TEXTBOOK_COLORS[index % TEXTBOOK_COLORS.length];
};
```

### Step 2: 修改 getChartOption 支持教材颜色模式

```typescript
const [colorMode, setColorMode] = useState<'category' | 'textbook'>('category');

// 在 getChartOption 中
const textbookIds = Array.from(new Set(graphData.nodes.map(n => n.textbook_id)));

data: filteredNodes.map(node => ({
  ...node,
  symbolSize: Math.max(20, Math.min(60, 20 + node.frequency * 10)),
  category: colorMode === 'category' ? categories.indexOf(node.category) : textbookIds.indexOf(node.textbook_id),
  itemStyle: {
    color: colorMode === 'category' 
      ? (CATEGORY_COLORS[node.category] || '#5470c6')
      : getTextbookColor(node.textbook_id, textbookIds),
  },
})),
```

### Step 3: 添加颜色模式切换按钮

```tsx
<Space style={{ width: '100%' }}>
  <Button
    type={colorMode === 'category' ? 'primary' : 'default'}
    onClick={() => setColorMode('category')}
  >
    按分类
  </Button>
  <Button
    type={colorMode === 'textbook' ? 'primary' : 'default'}
    onClick={() => setColorMode('textbook')}
  >
    按教材
  </Button>
</Space>
```

---

## Task 4: 添加全屏模式和缩放控制按钮

**Files:**
- Modify: `frontend/src/components/KnowledgeGraphPanel.tsx`

### Step 1: 添加全屏状态

```typescript
const [isFullscreen, setIsFullscreen] = useState(false);
const chartRef = useRef<ReactECharts>(null);
```

### Step 2: 添加控制按钮

```tsx
<Space style={{ position: 'absolute', right: 16, top: 16, zIndex: 10 }}>
  <Button onClick={() => chartRef.current?.getEchartsInstance().dispatchAction({ type: 'zoom', zoom: 1.1 })}>
    放大
  </Button>
  <Button onClick={() => chartRef.current?.getEchartsInstance().dispatchAction({ type: 'zoom', zoom: 0.9 })}>
    缩小
  </Button>
  <Button onClick={() => setIsFullscreen(!isFullscreen)}>
    {isFullscreen ? '退出全屏' : '全屏'}
  </Button>
</Space>
```

### Step 3: 修改容器样式支持全屏

```tsx
<Card 
  style={{ 
    flex: 1, 
    overflow: 'hidden',
    position: isFullscreen ? 'fixed' : 'relative',
    top: isFullscreen ? 0 : undefined,
    left: isFullscreen ? 0 : undefined,
    width: isFullscreen ? '100vw' : undefined,
    height: isFullscreen ? '100vh' : undefined,
    zIndex: isFullscreen ? 1000 : undefined,
  }}
>
```

---

## Task 5: 添加图谱查询分页支持

**Files:**
- Modify: `src/api/routes/kg.py`

### Step 1: 添加分页参数

```python
@router.get("/graph/{file_id}")
async def get_knowledge_graph(
    file_id: str,
    page: int = 1,
    page_size: int = 100,
    category: Optional[str] = None,
):
    """获取知识图谱数据（支持分页和筛选）"""
    graph = graph_store.load(file_id)
    
    if not graph:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")
    
    # 筛选
    nodes = graph.nodes
    if category:
        nodes = [n for n in nodes if n.category == category]
    
    # 分页
    total = len(nodes)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_nodes = nodes[start:end]
    
    # 获取相关的关系
    node_ids = {n.id for n in paginated_nodes}
    related_relations = [
        r for r in graph.relations 
        if r.source in node_ids or r.target in node_ids
    ]
    
    return {
        "nodes": [node.model_dump() for node in paginated_nodes],
        "links": [rel.model_dump() for rel in related_relations],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }
```

---

## Task 6: 编写单元测试

**Files:**
- Create: `tests/test_kg_extractor.py`
- Create: `tests/test_graph_store.py`

### test_graph_store.py 示例

```python
import pytest
import tempfile
import shutil
from pathlib import Path
from src.kg.graph_store import KnowledgeGraphStore
from src.kg.models import KnowledgeGraph, KnowledgeNode, KnowledgeRelation

@pytest.fixture
def temp_dir():
    """创建临时目录"""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def store(temp_dir):
    """创建存储实例"""
    return KnowledgeGraphStore(data_dir=temp_dir)

@pytest.fixture
def sample_graph():
    """创建示例图谱"""
    return KnowledgeGraph(
        textbook_id="test_book",
        textbook_title="测试教材",
        nodes=[
            KnowledgeNode(id="node_1", name="概念A", definition="定义A"),
            KnowledgeNode(id="node_2", name="概念B", definition="定义B"),
        ],
        relations=[
            KnowledgeRelation(source="node_1", target="node_2", relation_type="prerequisite"),
        ],
    )

def test_save_and_load(store, sample_graph):
    """测试保存和加载"""
    store.save("test_1", sample_graph)
    loaded = store.load("test_1")
    assert loaded is not None
    assert loaded.textbook_id == "test_book"
    assert len(loaded.nodes) == 2

def test_list_graphs(store, sample_graph):
    """测试列出图谱"""
    store.save("test_1", sample_graph)
    store.save("test_2", sample_graph)
    graphs = store.list_graphs()
    assert len(graphs) == 2

def test_delete(store, sample_graph):
    """测试删除"""
    store.save("test_1", sample_graph)
    assert store.delete("test_1") is True
    assert store.load("test_1") is None

def test_update_node(store, sample_graph):
    """测试更新节点"""
    store.save("test_1", sample_graph)
    success = store.update_node("test_1", "node_1", {"name": "新名称"})
    assert success is True
    loaded = store.load("test_1")
    assert loaded.nodes[0].name == "新名称"
```

---

## Task 7: 验证所有修复

### Step 1: 运行后端测试
Run: `python -m pytest tests/ -v`
Expected: 所有测试通过

### Step 2: 启动开发服务器
Run: `start-dev.bat` 或分别启动前后端

### Step 3: 手动测试
1. 选择教材文件，点击"提取知识图谱"
2. 验证节点点击显示详情
3. 验证边点击显示关系详情
4. 验证颜色模式切换
5. 验证全屏模式
6. 验证缩放控制

---

## Dependencies

- Task 1-5 可以并行进行
- Task 6 依赖 Task 1（需要测试 update 方法）
- Task 7 依赖所有其他任务

## Priority Order

1. **P0**: Task 1 (PUT API), Task 2 (边点击), Task 3 (教材颜色)
2. **P1**: Task 4 (全屏/缩放), Task 5 (分页)
3. **P2**: Task 6 (测试), Task 7 (验证)
