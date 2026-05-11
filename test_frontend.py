from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5174')
    page.wait_for_load_state('networkidle')
    
    # 截图
    page.screenshot(path='frontend_test.png', full_page=True)
    
    # 检查页面标题
    title = page.title()
    print(f"Page title: {title}")
    
    # 检查主要元素
    content = page.content()
    
    # 检查是否有知识图谱面板
    kg_panel = page.locator('text=知识图谱可视化')
    if kg_panel.count() > 0:
        print("Knowledge graph panel found!")
    else:
        print("Knowledge graph panel not found")
    
    # 检查是否有文件上传区域
    upload_area = page.locator('text=点击或拖拽文件到此区域上传')
    if upload_area.count() > 0:
        print("File upload area found!")
    else:
        print("File upload area not found")
    
    # 检查是否有功能面板
    func_panel = page.locator('text=功能面板')
    if func_panel.count() > 0:
        print("Function panel found!")
    else:
        print("Function panel not found")
    
    browser.close()
    print("Test completed!")
