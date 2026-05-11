# Automated Testing Strategy for Full-Stack FastAPI + React Applications

## Overview

This document provides production-quality testing patterns for full-stack applications with Python FastAPI backend and React frontend. It covers all phases of development from unit tests to end-to-end testing.

## Table of Contents

1. [Testing Pyramid](#testing-pyramid)
2. [Backend Testing (FastAPI)](#backend-testing-fastapi)
3. [Frontend Testing (React)](#frontend-testing-react)
4. [Integration Testing](#integration-testing)
5. [End-to-End Testing](#end-to-end-testing)
6. [Mocking External Services](#mocking-external-services)
7. [Test File Structure](#test-file-structure)
8. [CI/CD Integration](#cicd-integration)
9. [Coverage and Quality Gates](#coverage-and-quality-gates)

---

## Testing Pyramid

The testing pyramid provides a mental model for test distribution:

- **Unit Tests (~50-60%)**: Fast, isolated tests for pure functions, validators, reducers
- **Integration Tests (~30-50%)**: API endpoints with test DB, components with mocked API
- **End-to-End Tests (~10%)**: Critical user flows only (login, create, submit)

### Key Principles

- Test at the lowest sufficient layer: Unit test validators, integration test API endpoints
- Prefer integration tests for CRUD: They exercise routing, validation, business logic, and DB together
- E2E tests for critical flows only: Login, checkout, core user journeys
- Aim for 70-80% meaningful coverage: Quality over quantity

---

## Backend Testing (FastAPI)

### 1. Essential Dependencies

```bash
pip install pytest pytest-asyncio httpx pytest-cov pytest-mock respx faker
```

### 2. Async Test Client Setup

Use httpx.AsyncClient with ASGITransport for async FastAPI apps:

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest_asyncio.fixture
async def client():
    """Async test client - no HTTP server needed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Why httpx over TestClient:
- Async support: Native async (TestClient wraps in sync)
- Event loop: Uses test event loop (TestClient creates its own)
- In-process: Both are in-process
- API compatible: Both use requests-like API

### 3. Database Testing with Transaction Rollbacks

```python
# tests/conftest.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = "postgresql+asyncpg://test:test@localhost:5432/test_db"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()  # Roll back after each test

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()
```

### 4. Dependency Overrides

FastAPI dependency_overrides is the power feature for test isolation:

```python
# Override auth for testing
@pytest.fixture(autouse=True)
def override_auth():
    def fake_user():
        return {"sub": "test-user", "role": "admin"}
    app.dependency_overrides[get_current_user] = fake_user
    yield
    app.dependency_overrides.clear()  # Always clear!
```

### 5. Writing Effective API Tests

```python
import pytest

class TestCreateItem:
    """Organize by resource and HTTP method."""

    @pytest.mark.asyncio
    async def test_create_item_success(self, client):
        """Test happy path - valid data returns 201."""
        payload = {"title": "Hello", "speed": 1.25}
        resp = await client.post("/items", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Hello"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_item_invalid_data(self, client):
        """Test validation - invalid data returns 422."""
        payload = {"title": "T", "speed": "fast"}
        resp = await client.post("/items", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_duplicate(self, client):
        """Test conflict - duplicate returns 409."""
        payload = {"title": "Unique", "speed": 1.0}
        await client.post("/items", json=payload)
        resp = await client.post("/items", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_item_unauthorized(self, client):
        """Test auth - no token returns 401."""
        app.dependency_overrides.clear()
        resp = await client.post("/items", json={"title": "Test"})
        assert resp.status_code == 401
```

Always test both success and failure paths. Add boundary cases (empty strings, max values, nonexistent IDs).

### 6. pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short --cov=app --cov-report=term-missing"
markers = [
    "unit: Fast unit tests (no database or network)",
    "integration: Integration tests (use test database)",
    "slow: Slow tests (>1 second)",
    "auth: Tests for authentication endpoints",
]
```

### 7. pytest Marks for Selective Execution

```python
@pytest.mark.unit
def test_slug_validator():
    """Fast unit test - no DB needed."""
    assert validate_slug("my-post") == "my-post"
    assert validate_slug("My Post") is None

@pytest.mark.integration
@pytest.mark.auth
async def test_login_flow(client, user):
    """Integration test - uses test database."""
    resp = await client.post("/login", json={"email": "test@example.com", "password": "pass"})
    assert resp.status_code == 200
```

Run selectively:
```bash
pytest -m unit -v              # Fast feedback during development
pytest -m integration -v       # Integration tests only
pytest -m "fast or slow" -v    # All tests in CI
```

---

## Frontend Testing (React)

### 1. Essential Dependencies

```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

Or for Jest-based projects:
```bash
npm install --save-dev jest @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

### 2. Configuration

Vitest (recommended for Vite projects):

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/tests/setup.ts',
    css: true,
  },
});
```

```typescript
// src/tests/setup.ts
import '@testing-library/jest-dom';
import { expect, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});
```

Jest configuration:

```javascript
// jest.config.js
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterSetup: ['<rootDir>/src/setupTests.ts'],
  moduleNameMapper: {
    '\\.(css|less|scss)$': 'identity-obj-proxy',
    '\\.(jpg|jpeg|png|svg)$': '<rootDir>/src/__mocks__/fileMock.js',
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  coverageThreshold: {
    global: {
      branches: 70,
      functions: 70,
      lines: 70,
      statements: 70,
    },
  },
};
```

### 3. Query Priority (Accessibility-First)

React Testing Library enforces user-centric testing:

```typescript
// BEST - How screen readers find elements
screen.getByRole('button', { name: /submit/i })

// GOOD - For form inputs
screen.getByLabelText('Email')

// OK - For visible text
screen.getByText('Welcome back')

// LAST RESORT - Only when nothing else works
screen.getByTestId('submit-button')
```

### 4. Testing User Interactions

Always use userEvent over fireEvent:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('LoginForm', () => {
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    mockOnSubmit.mockReset();
    mockOnSubmit.mockResolvedValue(undefined);
  });

  it('submits form with valid credentials', async () => {
    const user = userEvent.setup();
    render(<LoginForm onSubmit={mockOnSubmit} />);

    await user.type(screen.getByLabelText('Email'), 'test@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(mockOnSubmit).toHaveBeenCalledWith({
      email: 'test@example.com',
      password: 'password123',
    });
  });

  it('shows error for invalid email', async () => {
    const user = userEvent.setup();
    render(<LoginForm onSubmit={mockOnSubmit} />);

    await user.type(screen.getByLabelText('Email'), 'invalid');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    expect(mockOnSubmit).not.toHaveBeenCalled();
  });
});
```

### 5. Testing Async Data Loading

```typescript
describe('UserProfile', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading state, then displays user data', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: 'Alice' }),
    } as Response);

    render(<UserProfile userId={1} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    await waitForElementToBeRemoved(() => screen.queryByText(/loading/i));

    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('shows error state on failure', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('Network error'));

    render(<UserProfile userId={1} />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

### 6. Custom Render with Providers

```typescript
// src/tests/test-utils.tsx
import { render, RenderOptions } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <BrowserRouter>
      <ThemeProvider>
        {children}
      </ThemeProvider>
    </BrowserRouter>
  );
}

function renderWithProviders(ui: React.ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { renderWithProviders as render };
```

### 7. Testing Custom Hooks

```typescript
import { renderHook, waitFor } from '@testing-library/react';

describe('useUserData', () => {
  it('fetches user data', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 1, name: 'Alice' }),
    } as Response);

    const { result } = renderHook(() => useUserData(1));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user?.name).toBe('Alice');
  });
});
```

---

## Integration Testing

### 1. Full-Stack Integration with Playwright

```typescript
// playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: 'http://localhost:5173',
  },
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'uvicorn app.main:app --port 8000 --env-file .env.test',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
    },
  ],
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
```

### 2. Auth State Reuse

```typescript
// e2e/global-setup.ts
import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto('http://localhost:5173/login');
  await page.getByLabel('Email').fill(process.env.TEST_USER_EMAIL!);
  await page.getByLabel('Password').fill(process.env.TEST_USER_PASSWORD!);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL('**/dashboard');

  await page.context().storageState({ path: 'playwright/.auth/user.json' });
  await browser.close();
}

export default globalSetup;
```

```typescript
// e2e/posts.spec.ts
import { test, expect } from '@playwright/test';

test.use({ storageState: 'playwright/.auth/user.json' });

test.describe('Post creation', () => {
  test('creates a new post', async ({ page }) => {
    await page.goto('/posts/new');
    await page.getByLabel('Title').fill('My Test Post');
    await page.getByLabel('Body').fill('Test content');
    await page.getByRole('button', { name: /publish/i }).click();

    await page.waitForURL('**/posts/**');
    await expect(page.getByText('My Test Post')).toBeVisible();
  });
});
```

### 3. API Contract Testing

```python
# tests/test_contract.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_openapi_schema_matches():
    """Verify API matches documented schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    # Verify key endpoints exist
    assert "/items" in schema["paths"]
    assert "post" in schema["paths"]["/items"]
    assert "get" in schema["paths"]["/items/{item_id}"]
```

---

## Mocking External Services

### 1. Mocking LLM APIs with respx

The OpenAI SDK uses httpx under the hood. Mock at the transport layer:

```python
import pytest
import respx
import httpx

@pytest.mark.asyncio
@respx.mock
async def test_openai_completion():
    """Mock OpenAI chat completion."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I help you today?"
                    }
                }],
                "usage": {"total_tokens": 25}
            }
        )
    )

    result = await call_openai("Say hello")
    assert "Hello" in result
    assert respx.calls.call_count == 1
```

### 2. Mocking Tool Calls

```python
@pytest.mark.asyncio
@respx.mock
async def test_agent_tool_call():
    """Mock an LLM response that triggers a tool."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "create_task",
                                "arguments": '{"title": "Buy groceries"}'
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }]
            }
        )
    )

    result = await agent.process("Create a task")
    assert result.tool_calls[0].function.name == "create_task"
```

### 3. Verifying Request Data

```python
@pytest.mark.asyncio
@respx.mock
async def test_request_verification():
    """Verify correct data is sent to OpenAI."""
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "Response"}}]
        })
    )

    await agent.process("Hello, agent!")

    assert route.called
    assert route.call_count == 1

    request = route.calls[0].request
    body = request.content.decode()
    assert "Hello, agent!" in body
    assert "gpt-4" in body
```

### 4. Mocking Multiple External Services

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def mock_s3():
    """Auto-applied to every test - prevents real S3 calls."""
    with patch("app.storage.s3.put_object") as mock:
        mock.return_value = {"ETag": '"fake-etag"'}
        yield mock

@pytest.fixture(autouse=True)
def mock_email():
    """Suppress all email sending in tests."""
    with patch("app.email.config.fast_mail.send_message",
               new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis for task queue."""
    with patch("app.main.create_arq_pool") as mock_pool:
        pool = AsyncMock()
        pool.enqueue_job = AsyncMock(return_value=None)
        mock_pool.return_value = pool
        yield pool
```

### 5. Frontend API Mocking with MSW

```typescript
// src/mocks/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      name: 'Test User',
      email: 'test@example.com',
    });
  }),

  http.post('/api/login', async ({ request }) => {
    const body = await request.json() as { email: string; password: string };

    if (body.email === 'test@example.com' && body.password === 'password') {
      return HttpResponse.json({ token: 'fake-jwt-token' });
    }
    return new HttpResponse(null, { status: 401 });
  }),
];
```

```typescript
// src/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

```typescript
// src/tests/setup.ts
import { server } from '../mocks/server';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

Override per test:

```typescript
it('handles API error', async () => {
  server.use(
    http.get('/api/users/:id', () => {
      return new HttpResponse(null, { status: 500 });
    })
  );

  render(<UserProfile userId={1} />);

  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument();
  });
});
```

---

## Test File Structure

```
project/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── items.py
│   │   │   └── users.py
│   │   ├── models/
│   │   └── services/
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py          # Shared fixtures
│       ├── unit/
│       │   ├── test_validators.py
│       │   ├── test_slug.py
│       │   └── test_utils.py
│       ├── integration/
│       │   ├── test_items_api.py
│       │   ├── test_users_api.py
│       │   └── test_auth_flow.py
│       └── contract/
│           └── test_openapi.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   └── UserProfile.tsx
│   │   ├── hooks/
│   │   │   └── useUserData.ts
│   │   └── __mocks__/
│   │       └── handlers.ts      # MSW handlers
│   └── tests/
│       ├── setup.ts             # Test setup
│       ├── test-utils.tsx       # Custom render
│       ├── unit/
│       │   ├── validators.test.ts
│       │   └── utils.test.ts
│       ├── components/
│       │   ├── LoginForm.test.tsx
│       │   └── UserProfile.test.tsx
│       └── hooks/
│           └── useUserData.test.ts
├── e2e/
│   ├── global-setup.ts
│   ├── posts.spec.ts
│   └── auth.spec.ts
├── playwright.config.ts
├── pyproject.toml
└── package.json
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests
        run: pytest -m unit -v

      - name: Run all tests with coverage
        env:
          TEST_DATABASE_URL: postgresql://test_user:test_pass@localhost/test_db
          SECRET_KEY: test-secret-key
        run: pytest --cov=app --cov-report=xml --cov-fail-under=85 -v

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  frontend:
    name: Frontend Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }

      - name: Install dependencies
        run: npm ci

      - name: Run tests with coverage
        run: npm run test:coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    needs: [backend, frontend]  # Only run if unit tests pass
    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/main'

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: e2e_db
        ports: ["5432:5432"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          npm ci
          npx playwright install --with-deps chromium

      - name: Run E2E tests
        env:
          DATABASE_URL: postgresql://test_user:test_pass@localhost/e2e_db
          TEST_USER_EMAIL: e2e@example.com
          TEST_USER_PASSWORD: test-password
        run: npx playwright test

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
```

---

## Coverage and Quality Gates

### Backend Coverage

```toml
# pyproject.toml
[tool.coverage.run]
source = ["app"]
omit = ["tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 85
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
]
```

### Frontend Coverage

```javascript
// jest.config.js
coverageThreshold: {
  global: {
    branches: 70,
    functions: 70,
    lines: 70,
    statements: 70,
  },
},
collectCoverageFrom: [
  'src/**/*.{ts,tsx}',
  '!src/**/*.d.ts',
  '!src/**/index.{ts,tsx}',
],
```

### Quick Reference

| Tool | Purpose |
|------|---------|
| pytest | Test runner, fixtures, parametrize, marks |
| pytest-asyncio | Async test functions and fixtures |
| pytest-cov | Coverage measurement and reporting |
| httpx.AsyncClient | Async HTTP tests against ASGI app |
| respx | Mock httpx requests (for LLM APIs) |
| unittest.mock | MagicMock, patch, AsyncMock |
| Vitest/Jest | Frontend test runner |
| React Testing Library | User-centric component testing |
| MSW | Mock Service Worker for API mocking |
| Playwright | End-to-end browser testing |
| GitHub Actions | CI/CD automation |

### Common Pitfalls and Solutions

| Symptom | Cause | Solution |
|---------|-------|----------|
| Tests are slow | Hitting real DB/APIs | Dependency overrides, mocks, transaction rollbacks |
| Flaky tests | Time/random/order deps | Fixed seeds, time injection, I/O isolation |
| Spec drift | Docs not updated | OpenAPI contract tests |
| Cleanup leaks | Unclosed sessions | yield fixtures, clear overrides |
| Act warnings | State updates not wrapped | Use waitFor or findBy queries |

---

## References

- FastAPI Testing Documentation: https://fastapi.tiangolo.com/tutorial/testing/
- FastAPI Async Tests: https://fastapi.tiangolo.com/advanced/async-tests/
- FastAPI Testing Dependencies: https://fastapi.tiangolo.com/advanced/testing-dependencies/
- React Testing Library Docs: https://testing-library.com/docs/react-testing-library/intro/
- Vitest Documentation: https://vitest.dev/
- Playwright Documentation: https://playwright.dev/
- RESPX Documentation: https://lundberg.github.io/respx/
- MSW Documentation: https://mswjs.io/
