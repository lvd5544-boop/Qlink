# QLink Frontend / QLink 前端

QLink 的 React + Vite 客户端。项目介绍、完整启动方式和产品边界请阅读 [根目录 README](../README.md)。

React + Vite client for QLink. See the [root README](../README.md) for the product overview, full-stack setup, and trust boundaries.

## Local development / 本地开发

```bash
npm ci
npm run dev
```

The development server expects the API at `/api`; the full Docker Compose stack provides the production-style proxy configuration.

开发服务默认通过 `/api` 访问后端；根目录的 Docker Compose 会提供与生产一致的反向代理。

## Quality gates / 质量门禁

```bash
npm test
npm run lint
npm run build
npm run e2e
```
