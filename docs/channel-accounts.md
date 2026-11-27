# Nối tài khoản các kênh (Cài đặt → Mạng xã hội)

Tài liệu cho chị (chủ cửa hàng) và người cài máy chủ: muốn Hàng Chọn tự đăng bài, đọc tin nhắn, đồng bộ đơn trên từng kênh
thì chị cần **có gì**, **nhập gì**, **token sống bao lâu** và **giới hạn** của từng nền tảng. Mọi điều dưới đây đọc từ
tài liệu chính thức ngày 26/11/2026 (đường dẫn ở từng mục). **Chưa thử với tài khoản thật nào** — lần đầu bật mỗi kênh,
chị thử bằng một bài/đơn nhỏ.

Màn hình: `/desk/cai-dat/mang-xa-hoi` (chỉ chị). Mỗi kênh một thẻ: trạng thái (Giả lập / Chưa nối / Đã nối thật + tên tài
khoản), công tắc **Giả lập ↔ Chạy thật**, các ô cần nhập, nút **Kiểm tra kết nối**, nút **Kết nối** với kênh phải cấp quyền
trên trang của nền tảng, và hướng dẫn từng bước (chữ trong thẻ lấy từ `api/app/integrations/channel_config.py`).

## Tóm tắt

| Kênh | Chị cần có | Chị nhập | Cách lấy token | Token sống | Tự làm mới | Kiểm tra kết nối gọi |
|---|---|---|---|---|---|---|
| Trang Facebook | Trang Facebook (không phải trang cá nhân/nhóm), ứng dụng Meta | ID Trang, mã Trang dài hạn; (khoá bí mật ứng dụng, mã xác minh webhook nếu nhận tin nhắn) | Dán tay (Graph API Explorer) | Mã Trang lấy từ mã người dùng dài hạn **không hết hạn** (mất khi đổi mật khẩu, gỡ quyền) | Không cần | `GET /{page-id}?fields=id,name` |
| Instagram | Tài khoản Instagram chuyên nghiệp liên kết với Trang | ID tài khoản IG (dùng chung mã Trang) | Dán tay | Như mã Trang | Không cần | `GET /{ig-user-id}?fields=id,username` |
| Threads | Ứng dụng Meta trường hợp sử dụng Threads, tài khoản Threads là người dùng thử | ID người dùng Threads, mã dài hạn | Dán tay (Graph API Explorer) | 60 ngày | **Có** — hằng ngày 4:20, mã cũ hơn 7 ngày thì `GET /refresh_access_token` | `GET graph.threads.net/v1.0/{id}?fields=id,username` |
| TikTok | Ứng dụng TikTok for Developers (Login Kit + Content Posting API, scope `user.info.basic`, `video.upload`, `video.list`) | Client key, client secret → bấm **Kết nối TikTok** | **OAuth** (bắt buộc) | Access 2 giờ · refresh 180 ngày (đổi mới mỗi lần) | **Có** — khi dùng (còn < 10 phút) và hằng ngày | `GET /v2/user/info/?fields=open_id,display_name` |
| Zalo OA | OA chị quản trị + ứng dụng Zalo liên kết OA | OA ID, ID ứng dụng, khoá bí mật ứng dụng, access token + refresh token OA; (khoá bí mật OA cho webhook) | Dán tay (API Explorer của Zalo) | Access 25 giờ · refresh 3 tháng, dùng một lần | **Có** — khi hết hạn; token mới lưu lại vào Cài đặt | Làm mới token một lần (chưa lấy tên OA) |
| Nhóm Zalo | — | — | Không có API | — | — | — (chị sao chép bài rồi dán vào nhóm) |
| Shopee | Ứng dụng Shopee Open Platform đã duyệt (Partner ID + key), tài khoản shop | Partner ID, Partner key → bấm **Kết nối Shopee** | **OAuth** (bắt buộc, đăng nhập shop + OTP) | Access 4 giờ · refresh 30 ngày, dùng một lần · quyền tối đa 365 ngày | **Có** — khi dùng và hằng ngày | `GET /api/v2/shop/get_shop_info` |
| TikTok Shop | App trên Partner Center (App key, App secret, Service ID), tài khoản người bán | App key, App secret, Service ID → bấm **Kết nối TikTok Shop** | **OAuth** (bắt buộc) | Access 7 ngày · refresh theo thời hạn chị cấp | **Có** — khi dùng và hằng ngày | `GET /authorization/202309/shops` (lấy luôn shop cipher) |

Địa chỉ chuyển hướng (Redirect URI) cho ba kênh OAuth: `<WEB_BASE_URL>/api/hooks/oauth/<kênh>` (vd
`https://hangchon.example/api/hooks/oauth/tiktok`) — thẻ hiện đúng địa chỉ để chị dán vào ứng dụng. TikTok bắt buộc `https`.

## Facebook Page

**Chị cần chuẩn bị:** một Trang Facebook chị có quyền tạo nội dung (`CREATE_CONTENT`); một ứng dụng trên
developers.facebook.com do chị làm quản trị; các quyền `pages_show_list`, `pages_manage_posts`,
`pages_manage_read_engagement`, `pages_manage_metadata`.

**Bước 1.** Mở Graph API Explorer, chọn ứng dụng, tick 4 quyền trên, bấm «Generate Access Token» (mã người dùng ngắn hạn).
**Bước 2.** Đổi sang mã người dùng dài hạn (Access Token Debugger → «Extend Access Token», hoặc
`GET /oauth/access_token?grant_type=fb_exchange_token&client_id&client_secret&fb_exchange_token`).
**Bước 3.** Với mã dài hạn, gọi `GET /me/accounts`: chép `id` (ID Trang) và `access_token` (mã Trang) vào thẻ.
**Bước 4.** Lưu → Kiểm tra kết nối (hiện tên Trang) → bật «Chạy thật».

Hệ thống lưu: `page_id`, `page_token` (mã hoá); tuỳ chọn `app_secret` (kiểm chữ ký webhook), `webhook_verify_token`.

Giới hạn: API chỉ đăng lên **Trang**, không đăng lên trang cá nhân hay nhóm Facebook. Ứng dụng chưa qua App Review chỉ
dùng với Trang của người có vai trò trong ứng dụng (đủ cho Trang của chị). Mã Trang mất hiệu lực khi đổi mật khẩu
Facebook, gỡ quyền ứng dụng hoặc mất vai trò trên Trang.
Vì mã Trang dài hạn dán tay là cách tài liệu Meta hướng dẫn (Graph API Explorer), Facebook **không cần nút Kết nối**.

Nguồn: [Bắt đầu với API Trang](https://developers.facebook.com/docs/pages-api/getting-started) ·
[Mã truy cập dài hạn](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived) ·
[Tham chiếu Page](https://developers.facebook.com/docs/graph-api/reference/page/).
Ghi chú: tài liệu hôm nay nói phiên bản Graph mới nhất là **v27.0**; máy chủ đang mặc định `META_GRAPH_VERSION=v24.0`.

## Instagram

**Chị cần chuẩn bị:** tài khoản Instagram **chuyên nghiệp** (doanh nghiệp hoặc nhà sáng tạo) liên kết với Trang ở trên;
quyền `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (API Instagram qua Đăng nhập bằng Facebook,
dùng mã Trang). «Ngừng bán» xoá hẳn bài Instagram cần thêm `instagram_manage_contents` (theo changelog Meta 12/2025, chưa
đối chiếu tài liệu tham chiếu, chưa thử thật); Instagram không có «ẩn bài».

**Bước 1.** Trong Graph API Explorer (mã Trang), gọi `GET /{ID Trang}?fields=instagram_business_account`.
**Bước 2.** Chép `id` vào ô «ID tài khoản Instagram công việc», Lưu → Kiểm tra (hiện @tên).

Hệ thống lưu: `ig_user_id`; mã dùng chung với thẻ Facebook.
Giới hạn: ảnh/video phải ở địa chỉ công khai lúc đăng; Trang cần «Ủy quyền đăng trên Trang» (PPA) thì phải làm xong trên
Facebook trước.

Nguồn: [Đăng nội dung](https://developers.facebook.com/docs/instagram-platform/content-publishing) ·
[IG User](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user).

## Threads

**Chị cần chuẩn bị:** ứng dụng Meta tạo với trường hợp sử dụng **Threads** (có ID + khoá bí mật ứng dụng Threads riêng);
tài khoản Threads của chị được mời làm «Người dùng thử Threads» và đã chấp nhận; quyền `threads_basic`,
`threads_content_publish` (thêm `threads_manage_insights` để xem số liệu; `threads_delete` nếu muốn «Ngừng bán» xoá hẳn
bài Threads — tối đa 100 lượt xoá / 24 giờ).

**Bước 1.** Bảng điều khiển ứng dụng → Vai trò → mời tài khoản Threads; chấp nhận trong Cài đặt Threads → Quyền.
**Bước 2.** Tạo mã người dùng (Graph API Explorer, máy chủ graph.threads.net), đổi sang mã dài hạn (`GET /access_token`).
**Bước 3.** Chép ID người dùng (`GET /me?fields=id,username`) và mã dài hạn vào thẻ; Lưu → Kiểm tra.

Token: ngắn hạn 1 giờ; dài hạn 60 ngày, làm mới được khi đã ≥ 24 giờ tuổi và còn hạn
(`GET /refresh_access_token?grant_type=th_refresh_token`). Hệ thống tự làm mới mã cũ hơn 7 ngày (việc nền hằng ngày).
Quyền chị cấp sống 90 ngày, chỉ tự gia hạn khi trang cá nhân Threads để **công khai**.

Nguồn: [Bắt đầu với API Threads](https://developers.facebook.com/docs/threads/get-started) ·
[Mã dài hạn](https://developers.facebook.com/docs/threads/get-started/long-lived-tokens) ·
[Trang cá nhân](https://developers.facebook.com/docs/threads/threads-profiles).

## TikTok (đẩy bản nháp)

**Chị cần chuẩn bị:** ứng dụng trên developers.tiktok.com có **Login Kit** và **Content Posting API**; được duyệt scope
`user.info.basic`, `video.upload` (thêm `video.list` để xem số liệu); Redirect URI đăng ký trong Login Kit (https, cố định,
không tham số); tên miền ảnh/video đã xác minh với TikTok (nguồn `PULL_FROM_URL`).

**Bước 1.** Tạo ứng dụng, thêm Login Kit + Content Posting API, dán Redirect URI của thẻ.
**Bước 2.** Chép Client key, Client secret vào thẻ, Lưu.
**Bước 3.** Bấm **Kết nối TikTok** → đăng nhập TikTok → đồng ý. Hệ thống đổi mã lấy token
(`POST https://open.tiktokapis.com/v2/oauth/token/`) và tự làm mới.

Vì sao phải bấm Kết nối: access token chỉ sống **2 giờ**, refresh token 180 ngày và **đổi mới mỗi lần làm mới** — dán tay
không dùng được. Hệ thống lưu `access_token`, `refresh_token`, `open_id` (mã hoá) và hạn token.
Giới hạn: Hàng Chọn chỉ **đẩy bản nháp** vào hộp thư TikTok, chị bấm đăng trong app; ứng dụng chưa qua kiểm duyệt
(audit) chỉ đăng được riêng tư.

Nguồn: [Login Kit cho web](https://developers.tiktok.com/doc/login-kit-web) ·
[Quản lý token](https://developers.tiktok.com/doc/oauth-user-access-token-management) ·
[Lấy token](https://developers.tiktok.com/docs/en/oauth-get-a-user-access-token) ·
[Làm mới token](https://developers.tiktok.com/docs/en/oauth-refresh-a-user-access-token) ·
[Đẩy nội dung](https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content) ·
[Get User Info](https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info).

## Zalo OA

**Chị cần chuẩn bị:** một Zalo Official Account chị quản trị; ứng dụng trên developers.zalo.me liên kết với OA, đã bật
nhóm quyền cần dùng (tin nhắn, bài viết, ZNS nếu báo tin cho khách).

**Bước 1.** Ứng dụng Zalo → Official Account: liên kết OA; chép ID ứng dụng, khoá bí mật ứng dụng.
**Bước 2.** Mở API Explorer của Zalo, chọn ứng dụng + OA, lấy access token và refresh token của OA.
**Bước 3.** Dán vào thẻ, Lưu → Kiểm tra (hệ thống làm mới token một lần để chắc khoá đúng).

Token: access token 25 giờ; refresh token 3 tháng, **dùng một lần** (mỗi lần làm mới nhận refresh token mới). Hệ thống
tự làm mới bằng `POST https://oauth.zaloapp.com/v4/oa/access_token` và lưu cặp token mới vào Cài đặt (mã hoá) để API,
worker, driver đăng bài/hộp thư và báo tin ZNS dùng chung.

⚠️ Trang tài liệu Zalo dựng bằng JavaScript, hôm nay **không tải lại được** để đối chiếu; thông tin trên lấy từ lần đọc
25/11/2026 ghi trong `api/app/integrations/_zalo_token.py`. Vì vậy chưa có nút «Kết nối Zalo» (OAuth v4 có PKCE) và
«Kiểm tra kết nối» chưa lấy được tên OA (điểm cuối `getoa` chưa đối chiếu). Cách dán token từ API Explorer vẫn dùng được.

Nguồn: [Xác thực và ủy quyền cho ứng dụng](https://developers.zalo.me/docs/official-account/bat-dau/xac-thuc-va-uy-quyen-cho-ung-dung-new) ·
[API Explorer](https://developers.zalo.me/tools/explorer).

## Nhóm Zalo

Zalo không có API đăng vào nhóm. Hàng Chọn soạn bài; chị bấm «Sao chép» ở mục Nội dung rồi dán vào nhóm.

## Shopee

**Chị cần chuẩn bị:** tài khoản nhà phát triển trên open.shopee.com, một App đã duyệt (Partner ID + Partner key); khai tên
miền của Redirect URI trong «Redirect URL Domain» của App; tài khoản shop của chị.

**Bước 1.** Console Shopee Open Platform → App: khai tên miền Redirect; chép Partner ID, Partner key vào thẻ, Lưu.
**Bước 2.** Bấm **Kết nối Shopee** → đăng nhập tài khoản shop, nhập OTP, đồng ý.
**Bước 3.** Shopee chuyển về kèm `code` + `shop_id`; hệ thống đổi mã (`POST /api/v2/auth/token/get`) và tự làm mới
(`POST /api/v2/auth/access_token/get`).

Token: access 4 giờ; refresh 30 ngày, dùng một lần; mỗi lần cấp quyền tối đa 365 ngày. Hệ thống làm mới mỗi ngày nên
refresh token không chết khi lâu không có đơn. Link cấp quyền ký bằng Partner key (hết hạn sau 5 phút — bấm Kết nối lại nếu
để lâu). Cấp quyền bằng **tài khoản shop** (tài khoản chính nhiều shop chưa hỗ trợ).

Nguồn: [Ủy quyền và xác thực](https://open.shopee.com/developer-guide/20) ·
[v2.shop.get_shop_info](https://open.shopee.com/documents/v2/v2.shop.get_shop_info?module=92&type=1).

## TikTok Shop

**Chị cần chuẩn bị:** tài khoản Partner Center TikTok Shop, một App cho người bán (App key, App secret, Service ID); Redirect
URL của App đặt đúng địa chỉ trong thẻ; tài khoản người bán.

**Bước 1.** Partner Center → App & Service: đặt Redirect URL; chép App key, App secret, Service ID vào thẻ, Lưu.
**Bước 2.** Bấm **Kết nối TikTok Shop** → đăng nhập người bán → đồng ý.
**Bước 3.** Hệ thống đổi mã (`GET https://auth.tiktok-shops.com/api/v2/token/get`, `grant_type=authorized_code`), lấy shop
cipher (`GET /authorization/202309/shops`) và tự làm mới (`…/api/v2/token/refresh`).

Token: access 7 ngày; refresh theo thời hạn chị chọn khi cấp; TikTok báo trước 30 ngày khi quyền sắp hết. Khi App còn đang
phát triển chỉ «cửa hàng phát triển» (Seller Center test account) cấp quyền được.

Nguồn: [Tổng quan ủy quyền](https://partner.tiktokshop.com/docv2/page/authorization-overview-202407) ·
[Hướng dẫn người bán cấp quyền](https://partner.tiktokshop.com/docv2/page/seller-authorization-guide) ·
[Get Authorized Shops](https://partner.tiktokshop.com/docv2/page/get-authorized-shops-202309).

## Lưu trữ và an toàn (cho người cài máy chủ)

- Lưu ở bảng `app_settings`, khoá `channel_account.<kênh>`. Ô bí mật mã hoá Fernet bằng `SECRETS_ENCRYPTION_KEY` (cùng
  cơ chế khoá AI); API chỉ trả 4 ký tự cuối; dòng này không hiện trong `GET /api/desk/control/settings`.
- Thứ tự: **Cài đặt > biến môi trường**. Công tắc Giả lập/Chạy thật của kênh trong Cài đặt thắng `SOCIAL_CHANNEL_DRIVERS`,
  `SOCIAL_DRIVER`, `MARKETPLACES_DRIVER`; kênh chưa bấm công tắc thì theo biến môi trường.
- API đọc lại sau mỗi lần lưu; worker đọc lại ở đầu mỗi job (tối đa 5 giây cũ).
- Lưu vết: `control.channel_account_saved` (tên ô đã đổi, công tắc), `control.channel_account_checked`,
  `control.channel_account_connected` — không ghi giá trị khoá. Lời báo lỗi của nền tảng được lọc khoá trước khi hiện.
- «Kết nối»: `state` ngẫu nhiên, dùng một lần, hết hạn 15 phút; điểm nhận `GET /api/hooks/oauth/{kênh}`.
- Làm mới token: khoá liên tiến trình bằng advisory lock của Postgres để API và worker không cùng tiêu một refresh token.
- Điểm cuối: `GET /api/desk/control/channels`, `PATCH /api/desk/control/channels/{kênh}`,
  `POST /api/desk/control/channels/{kênh}/check`, `POST /api/desk/control/channels/{kênh}/connect` (chỉ owner).
