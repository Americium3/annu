# CarePath Frontend

医疗设施推荐网站的 React 前端。默认连接 `backend/` 的真实推荐 API（Databricks 数据）；`VITE_USE_DEMO=true` 时使用内置演示数据。

## 本地运行

前端默认连接真实后端（`backend/`，FastAPI，端口 8000），Vite 会把 `/api` 代理过去。先按 `backend/README.md` 启动后端，再：

```bash
pnpm install
pnpm dev
```

没有后端时，可以用内置的演示数据运行：`VITE_USE_DEMO=true pnpm dev`。

默认访问 `http://127.0.0.1:5173`。

生产构建：

```bash
pnpm build
pnpm preview
```

## 已实现

- React 19 + TypeScript + Vite。
- 服务与地点搜索、服务建议、当前位置入口。
- 桌面端结果列表与 Leaflet 地图双栏联动。
- 移动端列表/地图切换，适配 390px 视口。
- 用户只输入两项：需要的服务和所在位置（城市、区县、PIN、坐标，或"使用我的位置"）。搜索半径、结果数量和排序都由推荐系统决定：从 25 km 开始，找不到就自动扩大到 200 km，结果按证据优先的规则排序。
- 推荐分数、证据引用、来源类型、不确定性提示。
- 详情抽屉中的评分拆分、原始证据、来源与缺失字段。
- 分享用搜索参数保存到 URL。
- `modelVersion`、`rankingVersion` 和可替换评分拆分结构。

## 数据说明

当前设施、证据和来源均为明确的演示数据。默认详细场景是 Bhubaneswar 附近的透析服务；选择其他服务时，前端会生成与服务匹配的模板化演示证据。所有内容都不能作为真实医疗服务可用性的依据。

推荐数据入口位于 `src/lib/api.ts`（真实的 `POST /api/recommendations`、`GET /api/services`、`GET /api/locations`）；`src/lib/demoApi.ts` 保留为演示模式。前端契约仍是 `src/types.ts`。ML 模型应继续返回总分、特征贡献或评分拆分、证据和不确定性。

## 目录

```text
src/
├── components/        # 页面业务组件
├── data/              # 演示设施、证据与来源
├── hooks/             # 响应式布局 Hook
├── lib/               # Mock 推荐 API
├── App.tsx            # 页面组合与搜索状态
└── types.ts           # 前端领域与推荐契约
```
