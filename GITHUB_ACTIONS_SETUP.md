# GitHub Actions + 阿里云 ACR 自动构建推送指南

复制以下内容即可在新项目中使用，无需改动代码。

---

## 1. 目录结构

在你的项目根目录创建：

```
.github/
└── workflows/
    └── build-push.yml
```

## 2. Workflow 文件

`.github/workflows/build-push.yml`

```yaml
name: Build & Push to Aliyun ACR

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

env:
  REGISTRY: registry.cn-hangzhou.aliyuncs.com
  NAMESPACE: docker-pusher          # 改成你的阿里云命名空间
  IMAGE: trendrod                   # 改成你的镜像仓库名

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Extract tag
        id: meta
        run: |
          if [[ "$GITHUB_REF" == refs/tags/* ]]; then
            TAG=${GITHUB_REF#refs/tags/}
          else
            TAG=latest
          fi
          echo "tag=$TAG" >> $GITHUB_OUTPUT

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Aliyun ACR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.ALIYUN_USERNAME }}
          password: ${{ secrets.ALIYUN_PASSWORD }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.NAMESPACE }}/${{ env.IMAGE }}:${{ steps.meta.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.NAMESPACE }}/${{ env.IMAGE }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## 3. GitHub Secrets 配置

进入仓库页面：

**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | 值 | 说明 |
|------|-----|------|
| `ALIYUN_USERNAME` | `aliyun3174025308` | 阿里云账号（镜像仓库配置中的用户名） |
| `ALIYUN_PASSWORD` | `Gong323329` | 阿里云镜像仓库密码 |

> 建议用 GitHub Personal Access Token 推送代码时，token 需要勾选 `repo` + `workflow` 权限。

## 4. 阿里云 ACR 创建仓库

1. 登录 https://cr.console.aliyun.com/
2. 进入你的命名空间（如 `docker-pusher`）
3. 点击 **创建镜像仓库**
4. 仓库名称填 workflow 中 `IMAGE` 的值（如 `trendrod`）
5. 类型选 **私有**，地区选 `cn-hangzhou`

## 5. 触发构建

### 方式一：推送 tag（推荐）

```bash
git tag v0.1.0
git push origin v0.1.0
```

构建完成后镜像地址：
```
registry.cn-hangzhou.aliyuncs.com/docker-pusher/trendrod:v0.1.0
registry.cn-hangzhou.aliyuncs.com/docker-pusher/trendrod:latest
```

### 方式二：手动触发

1. 打开仓库页面 → **Actions** → **Build & Push to Aliyun ACR**
2. 点击右侧 **Run workflow** → 选分支 `main` → **Run workflow**
3. 推送 `latest` tag

## 6. 服务器部署

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/docker-pusher/trendrod:latest
docker compose up -d
```

---

## 通用模板变量对照表

| 变量 | 当前值 | 新项目改这里 |
|------|--------|-------------|
| `NAMESPACE` | `docker-pusher` | 你的阿里云命名空间 |
| `IMAGE` | `trendrod` | 你的镜像仓库名 |
| `REGISTRY` | `registry.cn-hangzhou.aliyuncs.com` | 如需其他 region 可改 |

只需改 workflow 文件里的 `NAMESPACE` 和 `IMAGE`，其余完全通用。

---

## 常见问题

### Q1: 阿里云只有 `latest`，没有版本 tag（如 `v0.1.15`）

**原因**：tag 指向的是旧 commit，而 workflow 文件的修改在更新的 commit 上。GitHub Actions 检出的是 tag 指向的代码，所以运行的是旧版 workflow。

**解决**：把 tag 移到最新 commit 后重新 push。

```bash
# 本地删除 tag
git tag -d v0.1.15

# 在最新 commit 上重新打 tag
git tag -a v0.1.15 -m "v0.1.15 release"

# 删除远程旧 tag，推送新 tag
git push origin --delete v0.1.15
git push origin v0.1.15
```

### Q2: Actions 报错 `Password required`

**原因**：`ALIYUN_PASSWORD` secret 未设置或为空。

**解决**：检查仓库 **Settings → Secrets and variables → Actions** 中是否存在 `ALIYUN_PASSWORD`，且值为阿里云镜像仓库登录密码。

### Q3: Actions 报错 `invalid tag "refs/heads/main"`

**原因**：手动触发（`workflow_dispatch`）或分支 push 时，`GITHUB_REF` 的值是 `refs/heads/main`，直接当 tag 用会导致格式错误。

**解决**：workflow 中 tag 提取逻辑已加判断（见上方 YAML）：

```bash
if [[ "$GITHUB_REF" == refs/tags/* ]]; then
  TAG=${GITHUB_REF#refs/tags/}
else
  TAG=latest
fi
```

非 tag 触发时自动回退到 `latest`。
