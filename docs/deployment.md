# Triển khai Hàng Chọn lên Dokploy

Bản chạy thật là một ứng dụng **Docker Compose** trên Dokploy, dùng tệp [`docker-compose.prod.yml`](../docker-compose.prod.yml).
Mỗi lần gộp vào `main`, Dokploy tự build lại và chạy lại; API tự chạy `alembic upgrade head` trước khi nhận request.

```
Internet ── Traefik (Dokploy, HTTPS) ─┬─ https://<tên miền>/      → hangchon-web    :3000  (Next.js standalone)
                                      └─ https://<tên miền>/api/* → hangchon-api    :8000  (FastAPI, uvicorn)
                                                                     hangchon-worker        (arq: việc nền, cron)
                                                                     hangchon-postgres      (Postgres 16, volume pgdata)
                                                                     hangchon-redis         (Redis 7, volume redisdata)
                                         volume apidata:/data/storage ← tệp tải lên + bản sao lưu (api và worker dùng chung)
```

| Thành phần | Image | Ghi chú |
|---|---|---|
| `api`, `worker` | [`api/Dockerfile`](../api/Dockerfile) — cùng một image, khác lệnh chạy | Python 3.13 + uv, user `app` (không phải root), có `pg_dump` 16 (sao lưu) và `ffmpeg` (dựng video ngắn) |
| `web` | [`web/Dockerfile`](../web/Dockerfile) | bun cài gói + build, Node chạy `server.js` bản standalone, user `node` |
| `postgres`, `redis` | `postgres:16-alpine`, `redis:7-alpine` | không mở cổng ra máy chủ |

**Vì sao nối bằng tên container:** trên Dokploy nhiều ứng dụng dùng chung mạng `dokploy-network`. Tên dịch vụ trần
`postgres`/`redis` có thể trúng container của ứng dụng khác. Vì vậy mọi container có tên cố định `hangchon-*` và
`DATABASE_URL`/`REDIS_URL` trỏ vào `hangchon-postgres`/`hangchon-redis`. Muốn chạy hai bản trên cùng một máy (vd bản thử)
thì đặt `CONTAINER_PREFIX` khác nhau.

## 1. Thử trên máy trước khi đẩy

```bash
scripts/deploy-check.sh        # build 2 image, dựng compose prod (web :3900, api :8900), kiểm, rồi down -v
```

Script kiểm: mọi dịch vụ healthy, `/api/health`, đúng một head Alembic và CSDL đã ở head, API không chạy bằng root,
trang chủ và `robots.txt` (mang `SITE_URL`), rewrite `/api/*` của web, đăng nhập owner + cookie phiên, sao lưu bằng
`pg_dump`, worker trả lời `arq --check`. Không đụng bộ container dev (Postgres 5442, Redis 6382, API 8010, Web 3010).
Tuỳ chọn: `NO_CACHE=1` (build lại từ đầu), `KEEP=1` (giữ container để xem), `WEB_PORT=… API_PORT=…`.

## 2. Tạo ứng dụng trên Dokploy

1. **Project** → *Create Service* → **Compose** (kiểu *Docker Compose*, không phải *Stack*).
2. **Provider**: GitHub → repo Hàng Chọn → nhánh `main`. **Compose Path**: `./docker-compose.prod.yml`.
3. Bật **Autodeploy** (Dokploy tự deploy khi có commit mới trên `main`). Nếu repo nối bằng Git thường thay vì GitHub App:
   tab *Deployments* có URL webhook, khai vào GitHub → Settings → Webhooks (sự kiện *push*).
4. Tab **Environment**: dán các biến ở mục 3 (Dokploy ghi ra tệp `.env` cạnh tệp compose; compose đọc từ đó).
5. Tab **Domains**: thêm tên miền như mục 4.
6. **Deploy**. Lần đầu mất vài phút (build hai image). Xem log trong tab *Logs*; nếu tab này không hiện được
   (Dokploy khuyên không đặt `container_name`, ở đây đặt có chủ ý), dùng `docker logs hangchon-api` trên máy chủ.

> **Đổi biến môi trường xong phải bấm _Redeploy_, không phải _Restart_.** Restart chạy lại container cũ với env cũ.
> Riêng `SITE_URL` được ghi vào bản build của web (sitemap, robots, JSON-LD) nên càng phải Redeploy để build lại.

## 3. Biến môi trường

Sinh chuỗi ngẫu nhiên: `openssl rand -hex 32`. Không ghi giá trị thật vào repo (repo công khai).

### Bắt buộc

| Biến | Ý nghĩa |
|---|---|
| `SITE_URL` | Địa chỉ công khai, vd `https://hangchon.vn` (không có `/` cuối). Dùng làm `WEB_BASE_URL`, `CORS_ORIGINS`, đường dẫn tệp công khai, sitemap. |
| `POSTGRES_PASSWORD` | Mật khẩu Postgres. **Chỉ dùng chữ và số** (nó nằm trong `DATABASE_URL`, ký tự `@ : / ?` sẽ làm hỏng URL). `openssl rand -hex 24`. |
| `JWT_SECRET` | Khoá ký phiên đăng nhập (đóng vai `SECRET_KEY`), ≥ 32 ký tự ngẫu nhiên. Đổi khoá = mọi phiên đang mở bị đăng xuất. |
| `OWNER_EMAIL`, `OWNER_PASSWORD` | Tài khoản chị, tạo **một lần** khi API khởi động lần đầu. Sau đó đổi mật khẩu trong bàn làm việc; đổi biến này không đổi mật khẩu tài khoản đã có (nên thay bằng chuỗi ngẫu nhiên để khỏi lộ mật khẩu đầu). |
| `HOOKS_MOCK_SECRET` | Chữ ký webhook của driver mock. Khi `PAYMENTS_DRIVER`/`SHIPPING_DRIVER` còn là `mock`, webhook mock **vẫn mở** ở prod; giá trị mặc định nằm công khai trong repo nên phải đặt chuỗi riêng. |

### Nên đặt

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AI_PROVIDER` | `fake` | `anthropic` để dùng Claude thật (cần `ANTHROPIC_API_KEY`). `fake` = AI giả, chỉ để chạy thử. |
| `ANTHROPIC_API_KEY` | trống | Khoá Claude API. |
| `AI_MONTHLY_BUDGET_VND` | `1500000` | Trần chi phí AI mỗi tháng (VND); chạm trần thì mọi tác vụ AI dừng và tạo việc chờ chị. Chị đổi được trên giao diện (*Tự chủ → Chi phí AI*), giá trị trên giao diện ghi đè biến này. `0` = không giới hạn. |
| `AI_MODEL_SMART` / `AI_MODEL_FAST` | `claude-opus-5-5` / `claude-haiku-5-5` | Model cho tác vụ khó / nhanh. |
| `COOKIE_SECURE` | `true` | Cookie phiên chỉ gửi qua HTTPS. Chỉ đặt `false` khi chạy thử bằng HTTP. |
| `COOKIE_DOMAIN` | trống | Để trống (cookie theo đúng tên miền đang mở). |
| `HC_DEMO_ACTIONS` | trống | Cờ demo (hành động mẫu `demo.*`). **Để trống ở prod.** |
| `CREATE_OWNER_ON_STARTUP` | `true` | Tạo tài khoản chị nếu chưa có. |
| `UVICORN_WORKERS` | `1` | Số tiến trình API. Giữ `1` khi còn driver `mock` (driver mock giữ trạng thái trong bộ nhớ từng tiến trình). |
| `LOG_LEVEL` | `INFO` | |
| `JWT_EXPIRE_MINUTES` | `20160` | Thời hạn phiên (14 ngày). |
| `POSTGRES_USER`, `POSTGRES_DB` | `hangchon` | Chỉ đặt trước lần deploy đầu; đổi sau đó phải tự đổi trong CSDL. |
| `CONTAINER_PREFIX` | `hangchon` | Tiền tố tên container. |

Các biến của từng tích hợp ở mục 6. Danh sách đầy đủ (kèm mặc định) nằm ở khối `x-api-env` đầu tệp
[`docker-compose.prod.yml`](../docker-compose.prod.yml); biến nào không đặt thì dùng mặc định ở đó.
`DATABASE_URL`, `REDIS_URL`, `STORAGE_LOCAL_DIR`, `API_ORIGIN` do tệp compose tự dựng, không cần đặt.

## 4. Tên miền và HTTPS

Trỏ bản ghi DNS `A` (và `AAAA` nếu có) của tên miền về IP máy chủ Dokploy, rồi trong tab **Domains** thêm **hai** dòng
cùng một host:

| Host | Path | Service | Container port | HTTPS |
|---|---|---|---|---|
| `hangchon.vn` | `/` | `web` | `3000` | bật, Certificate: *Let's Encrypt* |
| `hangchon.vn` | `/api` | `api` | `8000` | bật, *Let's Encrypt* — **không** bật *Strip Path* |

- Dòng `/api` đưa thẳng API (webhook, tải ảnh/video lên, tải bản sao lưu) vào FastAPI, không đi vòng qua Next.js.
  Traefik ưu tiên luật dài hơn nên `/api/*` vào `api`, còn lại vào `web`. Cùng một host nên cookie phiên vẫn cùng origin.
- Thiếu dòng `/api` vẫn chạy (web tự chuyển tiếp `/api/*` sang `http://hangchon-api:8000`), nhưng mọi tệp tải lên đi qua
  hai chặng.
- `SITE_URL` phải đúng `https://<host>` này. Có tên miền `www` thì thêm một dòng `www.hangchon.vn` → `web` (hoặc chuyển hướng ở DNS).
- Sau khi gắn tên miền bấm **Redeploy** để Dokploy gắn nhãn Traefik vào container.

## 5. Webhook — khai ở trang quản lý của từng bên

Tất cả nằm dưới `https://<tên miền>/api/hooks/...` (thay `<tên miền>` bằng `SITE_URL`):

| Bên gửi | URL | Xác thực |
|---|---|---|
| SePay (chuyển khoản VietQR) | `/api/hooks/payments/sepay` | Kiểu chứng thực «API Key» = `SEPAY_WEBHOOK_SECRET` (SePay gửi `Authorization: Apikey <khoá>`) |
| Meta — Facebook Page, Messenger | `/api/hooks/social/facebook` | Verify token = `META_WEBHOOK_VERIFY_TOKEN`; chữ ký `X-Hub-Signature-256` bằng `META_APP_SECRET` |
| Meta — Instagram | `/api/hooks/social/instagram` | như trên (dùng chung một URL `/api/hooks/social/meta` cũng được) |
| Zalo OA | `/api/hooks/social/zalo_oa` | Chữ ký `X-ZEvent-Signature` bằng `ZALO_OA_SECRET` + `ZALO_APP_ID` |
| GHN | `/api/hooks/shipping/ghn` | GHN không ký; API hỏi lại GHN trạng thái vận đơn |
| GHTK | `/api/hooks/shipping/ghtk` | GHTK không ký; API hỏi lại GHTK trạng thái vận đơn |

Meta gọi `GET` (hub.challenge) để xác nhận khi đăng ký; webhook chỉ trả lời khi driver tương ứng đã cấu hình.
Webhook `mock` bị tắt ở prod, trừ khi driver đang chọn vẫn là `mock` (xem `HOOKS_MOCK_SECRET`).

## 6. Bật driver thật thay cho `mock`

Mọi tích hợp mặc định là `mock` để chạy trọn luồng không cần tài khoản. Bật từng cái bằng env rồi **Redeploy**.
Các driver thật đều **viết theo tài liệu công khai, chưa thử với tài khoản thật** — bật từng cái một và thử bằng đơn/bài nhỏ.

| Tích hợp | Biến bật | Khoá cần đặt |
|---|---|---|
| AI | `AI_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |
| Nguồn hàng | `SOURCES_DRIVER=web` (Claude + web search, cần AI thật) hoặc `onebound` (1688/Taobao) | `ONEBOUND_API_KEY`, `ONEBOUND_API_SECRET` |
| Thanh toán | `PAYMENTS_DRIVER=sepay` | `SEPAY_WEBHOOK_SECRET`, `SEPAY_API_KEY`, `BANK_CODE` (mã BIN hoặc VCB/MB…), `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME`, `PAYMENT_CODE_PREFIX` (khớp «Cấu hình mã thanh toán» trên SePay) |
| Vận chuyển | `SHIPPING_DRIVER=ghn` hoặc `ghtk` (hoặc bật hãng trong cài đặt «Hãng giao đang bật») | GHN: `GHN_TOKEN`, `GHN_SHOP_ID`. GHTK: `GHTK_TOKEN`, `GHTK_PICK_NAME`, `GHTK_PICK_TEL`, `GHTK_PICK_ADDRESS`, `GHTK_PICK_DISTRICT`, `GHTK_PICK_WARD`. Chung: `SHIPPING_FROM_PROVINCE`. Môi trường thử của hãng: `GHN_ENV=dev` / `GHTK_ENV=dev` |
| Đăng bài | `SOCIAL_PUBLISH_DRIVERS=facebook=meta_publish,instagram=meta_publish,threads=meta_publish,tiktok=tiktok_draft_publish,zalo_oa=zalo_oa_publish` (kênh không khai dùng `SOCIAL_DRIVER`, mặc định `mock`) | Meta: `META_APP_ID`, `META_APP_SECRET`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `META_IG_USER_ID`, `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN`, `META_GRAPH_VERSION`. TikTok: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN`. Zalo: `ZALO_OA_ID`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_AUTHOR`, `ZALO_OA_BROADCAST=1` (gửi bài luôn) |
| Hộp thư (bình luận, tin nhắn) | không có biến bật: đặt khoá rồi khai webhook (mục 5); tài khoản kênh tự tạo với driver `meta`/`zalo_oa` khi tin đầu tiên tới | `META_APP_SECRET`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `META_IG_USER_ID`, `META_WEBHOOK_VERIFY_TOKEN`; Zalo: `ZALO_APP_ID`, `ZALO_OA_ID`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_SECRET` |
| Sàn | `MARKETPLACES_DRIVER=shopee` hoặc `tiktok_shop` (khung driver: kéo đơn, cập nhật tồn) | Shopee: `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_SHOP_ID`, `SHOPEE_ACCESS_TOKEN`. TikTok Shop: `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`, `TIKTOK_SHOP_ACCESS_TOKEN`, `TIKTOK_SHOP_CIPHER` |
| Lưu tệp | `STORAGE_DRIVER=s3` (S3, R2, MinIO; chưa kiểm chứng) | `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` |
| Báo khách (`NOTIFY_DRIVER`), hoá đơn điện tử (`EINVOICE_DRIVER`) | — | Hiện chỉ có `mock`; email (`SMTP_*`) và Zalo OA cho báo khách chưa có driver. |

Token Zalo OA, Meta, sàn hết hạn theo thời gian; làm mới token là việc của người vận hành (đổi biến rồi Redeploy).

## 7. Sao lưu và khôi phục

**Trong ứng dụng:** worker tự sao lưu lúc 03:15 (giờ Việt Nam) mỗi ngày; chị bấm thêm ở *Bàn làm việc → Cài đặt → Sao lưu*.
Mỗi lần chạy `pg_dump` → gzip → lưu ở
`private/backups/…` trong volume `apidata`, giữ 14 bản gần nhất (đổi trong cài đặt). Tải về từ cùng màn hình.

Bản sao lưu nằm **cùng máy chủ** với dữ liệu: định kỳ tải về hoặc chép ra nơi khác. Trên máy chủ:

```bash
# CSDL: bản SQL nén, chép ra ngoài máy
docker exec hangchon-postgres pg_dump -U hangchon --no-owner --no-privileges hangchon | gzip > hangchon-$(date +%F).sql.gz
# Tệp tải lên + các bản sao lưu trong ứng dụng (volume apidata, gắn ở /data của api)
docker run --rm --volumes-from hangchon-api -v "$PWD":/out alpine tar czf /out/hangchon-files-$(date +%F).tgz -C /data storage
```

Nếu bản Dokploy đang dùng có *Volume Backups* tới S3 thì đặt lịch cho volume `pgdata` (hoặc dùng bản `pg_dump` ở trên) và `apidata`.

**Khôi phục CSDL** từ một tệp `.sql.gz` (của ứng dụng hoặc lệnh trên):

```bash
docker stop hangchon-worker hangchon-api
docker exec -i hangchon-postgres psql -U hangchon -d postgres -c "DROP DATABASE hangchon WITH (FORCE)" -c "CREATE DATABASE hangchon"
gunzip -c hangchon-YYYY-MM-DD.sql.gz | docker exec -i hangchon-postgres psql -U hangchon -d hangchon -v ON_ERROR_STOP=1
docker start hangchon-api hangchon-worker      # API chạy alembic upgrade head nếu bản sao lưu cũ hơn code
```

**Khôi phục tệp:** `docker run --rm --volumes-from hangchon-api -v "$PWD":/in alpine tar xzf /in/hangchon-files-….tgz -C /data`.

Thử khôi phục định kỳ trên máy khác (hoặc bằng `KEEP=1 scripts/deploy-check.sh`) — bản sao lưu chưa khôi phục thử là chưa chắc dùng được.

## 8. Danh sách kiểm trước khi mở bán thật

- [ ] `SITE_URL` đúng tên miền HTTPS; mở được `https://<tên miền>/` và `https://<tên miền>/api/health` → `{"status":"ok"}`.
- [ ] Đăng nhập bằng `OWNER_EMAIL` rồi **đổi mật khẩu owner** trong bàn làm việc; thay `OWNER_PASSWORD` trong Dokploy bằng chuỗi ngẫu nhiên.
- [ ] `JWT_SECRET`, `POSTGRES_PASSWORD`, `HOOKS_MOCK_SECRET` là chuỗi ngẫu nhiên riêng, không lấy từ ví dụ hay `.env.example`.
- [ ] `COOKIE_SECURE=true` (mặc định), `COOKIE_DOMAIN` trống.
- [ ] **Tắt cờ demo:** `HC_DEMO_ACTIONS` trống; không chạy `python -m app.seed` hay dữ liệu mẫu trên prod (nếu đã chạy thử thì xoá dữ liệu mẫu trước khi mở bán).
- [ ] `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`; đặt **trần chi phí AI** (`AI_MONTHLY_BUDGET_VND` hoặc trên *Tự chủ → Chi phí AI*) và kiểm một tác vụ AI chạy được.
- [ ] Mức tự chủ AI vẫn «thận trọng»: mọi thứ khách nhìn thấy đều chờ chị duyệt (*Tự chủ*).
- [ ] **Không mở bán khi `PAYMENTS_DRIVER=mock`**: webhook mock vẫn ghi nhận «đã trả tiền». Bật `sepay`, chuyển khoản thử một đơn nhỏ, thấy đơn tự chuyển «đã trả».
- [ ] Thông tin ngân hàng thật: `BANK_CODE`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME` (mã QR trên trang đặt hàng hiện đúng).
- [ ] Vận chuyển thật (`ghn`/`ghtk`) đã tạo thử một vận đơn và nhận được webhook trạng thái.
- [ ] Webhook đã khai ở SePay, Meta, Zalo OA, hãng giao (mục 5).
- [ ] Chạy *Sao lưu* một lần thành công và tải được tệp về; có lịch chép bản sao lưu ra ngoài máy chủ.
- [ ] `docker ps` thấy 5 container `hangchon-*` ở trạng thái `healthy`.

## 9. Vận hành

- **Deploy:** gộp vào `main` → Dokploy build lại → API kiểm đúng **một** head Alembic (nhiều head thì dừng, không migrate)
  → `alembic upgrade head` → uvicorn. Worker chỉ khởi động sau khi API healthy (đã migrate xong).
- **Migration:** sau khi lên prod, mỗi tính năng một tệp mới trong `api/alembic/versions/`, không sửa tệp cũ, mã revision ≤ 32 ký tự.
- **Lệnh trong container:** `docker exec -it hangchon-api alembic current` · `docker exec -it hangchon-api python -m app.seed`
  (chỉ khi cần dữ liệu khởi đầu) · `docker exec -it hangchon-postgres psql -U hangchon hangchon`.
- **Healthcheck:** api `GET /api/health`, web `GET /robots.txt`, worker `arq --check`, postgres `pg_isready`, redis `ping`.
  Mọi dịch vụ `restart: unless-stopped`.
- **CI:** [`ci/github-actions-ci.yml`](../ci/github-actions-ci.yml) (**chưa bật**: quyền đẩy code hiện tại không được phép tạo workflow; để bật, chép file này vào `.github/workflows/ci.yml` bằng tài khoản có quyền `workflow`, ví dụ sau khi chạy `gh auth refresh -s workflow`) chạy ruff + pytest (Postgres + Redis thật) và
  typecheck + lint + test + build của web khi push/PR vào `main`. Dokploy không chờ CI: kiểm xanh trước khi gộp.
