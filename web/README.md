# CarePath Frontend

医疗设施推荐网站的 React 前端原型。当前版本使用 Mock 数据，已按未来接入后端推荐 API 和 ML 排序模型的方式拆分界面与数据类型。

## 本地运行

```bash
pnpm install
pnpm dev
```

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
- Best match、Nearest、Most evidence 三种排序模式。
- 距离与置信度筛选。
- 推荐分数、证据引用、来源类型、不确定性提示。
- 详情抽屉中的评分拆分、原始证据、来源与缺失字段。
- 分享用搜索参数保存到 URL。
- `modelVersion`、`rankingVersion` 和可替换评分拆分结构。

## 主题 / Theme

All colours, type sizes, radii and shadows are tokens in the `:root` block at the top of `src/index.css` ("Calm clinic"). Components read only tokens, so changing the theme means editing that one block.

- **Light and dark.** The page follows the OS setting. The header's moon/sun button overrides it, and the choice is saved in `localStorage` (`carepath-theme`). `index.html` applies the saved choice before first paint so the page doesn't flash.
- **One action colour.** Deep teal (`--brand`) means "you can press this". Warm colours are used only for caution states and small decorative details, never for buttons.
- **Status is never colour alone.** Good / caution / critical always come with an icon and a word. Every text token meets WCAG AA (≥ 4.5:1) on every surface in both modes.
- **Readable sizes.** No text is smaller than 12px (`--fs-2xs`).

The direction comes from Sprout's landing page: calm, high-brightness and low-saturation surfaces, dark text, and one obvious next step.

## 数据说明

当前设施、证据和来源均为明确的演示数据。默认详细场景是 Bhubaneswar 附近的透析服务；选择其他服务时，前端会生成与服务匹配的模板化演示证据。所有内容都不能作为真实医疗服务可用性的依据。

推荐数据入口位于 `src/lib/demoApi.ts`。未来接入后端时，可用真实的 `POST /api/recommendations` 客户端替换该函数，同时保持 `src/types.ts` 中的前端契约不变。ML 模型应继续返回总分、特征贡献或评分拆分、证据和不确定性。

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
