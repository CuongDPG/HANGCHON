# Nối nguồn hàng (Cài đặt → Nguồn hàng)

Tài liệu cho chị (chủ cửa hàng) và người cài máy chủ: muốn Hàng Chọn săn hàng, đọc link, tìm bằng ảnh trên **sàn thật**
thì từng sàn đi được đường nào, chị cần **đăng ký gì**, **tốn bao nhiêu**, và **chỗ nào chưa kiểm chứng được**.
Tra cứu ngày 26/11/2026. **Chưa thử với khoá thật nào.** Nhiều trang chính thức không mở được hôm nay (ghi rõ ở từng mục),
nên một phần thông tin lấy từ bài viết của bên thứ ba. Lần đầu bật mỗi đường, chị bấm «Kiểm tra kết nối» rồi săn thử một đề nhỏ.

Màn hình: `/desk/cai-dat/nguon-hang` (chỉ chị). Phần trên: mỗi sàn một thẻ. Chị chọn **Giả lập**, **AI tìm trên web**
hoặc **Qua <dịch vụ>**. Phần dưới: mỗi dịch vụ cần khoá một thẻ, gồm ô nhập, nút «Kiểm tra kết nối», hướng dẫn từng bước và
chi phí. Chữ trong thẻ lấy từ `api/app/integrations/source_config.py`.

## Tóm tắt

| Sàn | API chính thức cho người bán ở VN? | Đường Hàng Chọn dùng | Chị cần đăng ký | Chi phí |
|---|---|---|---|---|
| 1688 | **Không**: open.1688.com cấp API lõi cho doanh nghiệp Trung Quốc (giấy phép, ngân hàng TQ)¹ | **OneBound** (trung gian) hoặc AI tìm trên web | Tài khoản open.onebound.cn, nạp tiền | Theo lần gọi (xem bảng giá OneBound) |
| Taobao / Tmall | **Không**: open.taobao.com cần xác minh danh tính TQ và duyệt ứng dụng¹ | **OneBound** hoặc AI tìm trên web (hay bị bắt đăng nhập) | Như trên | Như trên |
| Pinduoduo | Không tìm được đường cho người nước ngoài | AI tìm trên web (đọc được rất ít) | — | Tiền AI |
| Alibaba.com | Không thấy API tìm hàng cho người mua | AI tìm trên web | — | Tiền AI |
| Rakuten Ichiba | **Có**, miễn phí (Rakuten Web Service) | **Rakuten API** hoặc AI tìm trên web | Rakuten ID + ứng dụng trên Developer Dashboard | Miễn phí |
| Amazon Nhật | PA-API 5 đã ngừng; Creators API cần Amazon Associates Nhật | AI tìm trên web (chưa nối Creators API) | — | Tiền AI |

¹ Theo bài viết bên thứ ba, chưa đọc được trang chính thức (open.taobao.com chặn công cụ đọc trang).

**Khuyến nghị cho chị:** (1) Rakuten → «Qua Rakuten API» (miễn phí). (2) 1688, Taobao, Tmall → «Qua OneBound» khi đã
có tài khoản. Trong lúc chưa có thì dùng «AI tìm trên web» và chấp nhận kết quả thưa. (3) Pinduoduo, Alibaba.com,
Amazon Nhật → «AI tìm trên web». Phương án dự phòng cho OneBound là **TMAPI** (khoá ở header, có lượt dùng thử). Hàng Chọn
chưa viết driver TMAPI vì chưa xác minh được điểm cuối tìm kiếm.

## Cách chọn đường cho từng sàn

- Thẻ sàn có công tắc **Giả lập · AI tìm trên web · Qua <dịch vụ>**. Rời «Giả lập» thì hệ thống hỏi xác nhận (tốn tiền AI
  hoặc tiền gọi API).
- Sàn chị chưa chọn thì theo `SOURCES_DRIVER` của máy chủ. Nếu driver đó không lấy được sàn ấy (vd `onebound` với
  Rakuten), sàn dùng `web`; riêng `mock` thì vẫn là giả lập.
- Sàn không có thẻ (Amazon Mỹ, Tiểu Hồng Thư, @cosme), xu hướng, giá sàn Việt Nam và link trang lạ dùng «AI tìm trên
  web» khi có ít nhất một sàn chạy thật. Nếu mọi sàn đều giả lập thì những việc này cũng giả lập.
- Kỹ thuật: khi đã có lựa chọn trong Cài đặt, `get_driver("sources")` trả driver `routed`. Driver này chia từng việc
  theo sàn: tìm theo từ khoá, tìm bằng ảnh, đọc link, đọc đánh giá. Khi chưa có lựa chọn nào, hệ thống chạy đúng như
  trước (`SOURCES_DRIVER`).

## OneBound (1688, Taobao, Tmall), dịch vụ trung gian

**Chị cần chuẩn bị:** tài khoản trên open.onebound.cn và đã nạp tiền hoặc mua gói cho Taobao + 1688. Cần bật các API
`item_search` (tìm từ khoá), `item_get` (chi tiết), `item_search_img` + `upload_img` (tìm bằng ảnh), `item_review`
(đánh giá).

**Bước 1.** Đăng ký trên open.onebound.cn. **Bước 2.** Chọn gói Taobao/1688, nạp tiền, lấy API key + API secret.
**Bước 3.** Dán vào thẻ OneBound, Lưu → Kiểm tra kết nối (gọi một lần `item_get` món mẫu). **Bước 4.** Ở thẻ 1688 /
Taobao / Tmall chọn «Qua OneBound».

Cách gọi, đã đọc trong tài liệu OneBound: `GET https://api-gw.onebound.cn/<nền tảng>/<api>/?key=…&secret=…&<tham số>`.
Tham số chung là `cache`, `result_type`, `lang`. Ví dụ tài liệu cho `item_get`: `num_iid=520813250866`. Mã
`error_code` `0000` là thành công. Theo bài viết bên thứ ba, `2000` là không có kết quả nhưng **vẫn tính phí**, còn
`4000` là lỗi máy chủ và không tính phí. Tài liệu chính thức có cảnh báo rằng gọi kèm tham số thừa vẫn bị tính phí.

**Chưa kiểm chứng:** bảng giá; đăng ký bằng email hay WeChat; có bắt nạp tiền trước không; tham số của `item_review`
và `upload_img` (trang tài liệu báo lỗi 502 hôm nay). Các tham số này đang viết theo bản cũ của driver. Nếu gói của chị
không gồm `item_review`, hồ sơ vẫn chạy, chỉ thiếu đánh giá. Khoá đi trong URL (cách của OneBound), nên máy chủ tắt log
URL của `httpx` và lọc khoá khỏi mọi câu báo lỗi.

Nguồn: [OneBound](https://open.onebound.cn/) ·
[taobao.item_search](https://open.onebound.cn/help/api/taobao.item_search.html).

## Rakuten Web Service (Rakuten Ichiba)

**Chị cần chuẩn bị:** Rakuten ID (miễn phí) và một ứng dụng trên Rakuten Developers → Developer Dashboard. Khi tạo ứng
dụng, chị khai tên miền website của mình.

**Bước 1.** Đăng nhập Rakuten Developers, mở Developer Dashboard, tạo ứng dụng mới. **Bước 2.** Khai tên miền website.
**Bước 3.** Chép Application ID (dạng UUID) và Access key (`pk_…`) vào thẻ, Lưu → Kiểm tra kết nối (tìm thử 1 món).
**Bước 4.** Ở thẻ Rakuten chọn «Qua Rakuten API».

Năm 2026 Rakuten chuyển API sang địa chỉ mới **`openapi.rakuten.co.jp`**. Địa chỉ mới cần thêm **Access key**. Mã
ứng dụng dạng số kiểu cũ không còn dùng được, chị phải đăng ký lại; các bài viết ghi ngày tắt địa chỉ cũ khác nhau,
quanh 02–05/2026. Driver gọi
`GET https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601` với `applicationId`, `accessKey` (ở cả
header và tham số), `keyword` / `itemCode`, `hits` ≤ 30, `page`, `minPrice` / `maxPrice` (yên), `sort=standard`,
`imageFlag=1`, `format=json`, `formatVersion=2`. Driver gửi kèm `Referer` + `Origin` bằng tên miền đã khai, vì có bài
báo lỗi 403 khi thiếu Referer. Lỗi 403 nghĩa là sai khoá hoặc sai tên miền; 429 là gọi quá nhanh (khoảng 1 lần/giây).

Rakuten API dùng cho tìm theo từ khoá và chi tiết theo link `item.rakuten.co.jp/<cửa hàng>/<món>/`. Tìm bằng ảnh, đánh
giá, xu hướng thì đi «AI tìm trên web». Chưa xác minh API đánh giá của Ichiba còn chạy hay không.

⚠️ Hôm nay trang tài liệu chính thức trả **503**. Điểm cuối, tham số và cách gửi Access key ở trên lấy từ các bài viết
kỹ thuật (Qiita, issoh.co.jp, mô tả actor Apify) về đợt chuyển API. Có bài cho rằng sắp có phiên bản `20260701`. Chưa xác
minh: có cần số điện thoại Nhật khi đăng ký không, và Rakuten kiểm tên miền hay IP với ứng dụng chạy trên máy chủ.

Nguồn: [Rakuten Developers](https://webservice.rakuten.co.jp/) ·
[Ichiba Item Search](https://webservice.rakuten.co.jp/documentation/ichiba-item-search) (503 hôm nay) ·
[Qiita: chuyển API Rakuten 2026](https://qiita.com/StreamSolty/items/2a2a203cbc37fefdc115) ·
[issoh: chuyển API Rakuten](https://www.issoh.co.jp/tech/details/19877/).

## Taobao / Tmall / 1688 chính thức

- **1688 (open.1688.com):** theo một bài viết bên thứ ba, API lõi chỉ cấp cho **doanh nghiệp**. Hồ sơ gồm giấy phép kinh
  doanh có đóng dấu, CMND người đại diện pháp luật, tài khoản ngân hàng công ty và tài khoản 1688 có 诚信通. Cá nhân
  không xin được quyền API lõi. API xuyên biên giới cần thêm quyền xuất nhập khẩu. Thời gian duyệt 5–7 ngày làm việc.
  Bài này không nói tới API tìm bằng ảnh.
  Nguồn: [juejin.cn](https://juejin.cn/post/7549888200229077027).
- **Taobao (open.taobao.com, TOP):** cần xác minh danh tính, và dùng thương mại cần Taobao cấp phép. Chưa đọc được tài
  liệu chính thức vì trang chặn công cụ đọc. Nguồn: [developer.aliyun.com](https://developer.aliyun.com/article/1683655).
- **Kết luận:** với hộ kinh doanh ở Việt Nam, không có pháp nhân Trung Quốc thì **không khả thi**. Các công ty đặt hàng
  Trung Quốc ở Việt Nam thường dùng API trung gian (OneBound, TMAPI, OTAPI…).

## API trung gian khác (chưa viết driver)

| Dịch vụ | Xác thực | Giá | Đã kiểm chứng | Ghi chú |
|---|---|---|---|---|
| **TMAPI** (tmapi.top) | Header `apikey: <khoá>`; tạo khoá ở console.tmapi.io | Chưa rõ; tài khoản mới có lượt thử | Có `GET http://api.tmapi.top/taobao/item_detail?item_id=…` | Chưa thấy đường dẫn tìm từ khoá 1688/Taobao, tìm ảnh, đánh giá: **đừng viết code theo đoán**. Phương án 2 nếu OneBound không ổn |
| **OTAPI / OT Commerce** | Khoá instance | Trả trước $150–600 + $0,001–0,012 mỗi lần gọi, tối thiểu ~$150/tháng; tìm ảnh là phần thêm; thử 5 ngày | Bảng giá (otcommerce.com/key-payments) | Đắt cho một người bán |
| RapidAPI, Apify, LovBuy, DajiAPI | — | — | Chưa đọc | Có các actor Apify cào Taobao/1688; chưa đánh giá độ tin cậy |

Nguồn: [TMAPI bắt đầu](https://tmapi.top/docs/start) · [OT Commerce bảng giá](https://otcommerce.com/key-payments/).

## Alibaba.com, Pinduoduo, Amazon Nhật

- **Alibaba.com:** không tìm được tài liệu chính thức về API tìm hàng cho người mua (không kiểm chứng được). Hàng Chọn dùng
  «AI tìm trên web»; phần lớn trang sản phẩm Alibaba.com xem được công khai.
- **Pinduoduo:** không tìm được điều kiện đăng ký open.pinduoduo.com / Duoduo Jinbao cho người nước ngoài (không kiểm chứng
  được). Trang Pinduoduo chủ yếu mở trong app, nên AI đọc được rất ít.
- **Amazon Nhật:** Amazon thông báo **PA-API 5 đã ngừng**, ứng dụng còn gọi sẽ nhận lỗi 403. API thay thế là
  **Creators API**: đăng nhập OAuth 2.0 bằng Credential ID + Secret, cần là Amazon Associate ở đúng thị trường đó. Các
  nguồn ghi ngày ngừng khác nhau (30/04 hoặc 15/05/2026). Chưa xác minh: điều kiện doanh số, và người ở ngoài Nhật có đăng
  ký Associates Nhật được không. Hàng Chọn chưa nối và dùng «AI tìm trên web».
  Nguồn: [Amazon: PA-API 5 ngừng](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation) ·
  [Chuyển sang Creators API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi).

## «AI tìm trên web» (driver `web`, không cần tài khoản sàn)

Chỉ cần AI thật (Claude hoặc OpenRouter) ở *Cài đặt → AI*. Khi AI còn giả lập, thẻ báo kết quả là dữ liệu mẫu.

- **Làm được:** tìm tin rao bằng `web_search` (`site:<sàn>`) và đọc trang công khai bằng `web_fetch`. Kết quả tốt với
  Rakuten, Amazon Nhật, Alibaba.com và phần lớn trang bán lẻ.
- **Không làm được:** `web_fetch` không chạy JavaScript và không đăng nhập. Nó chỉ đọc URL đã xuất hiện trong cuộc trò
  chuyện, bị robots.txt chặn và nhận tối đa URL 250 ký tự (hệ thống rút gọn link trước, xem «Cấu hình nâng cao»). Theo các nhà cung cấp công cụ cào dữ liệu, từ 2025 trang
  `s.taobao.com`, `item.taobao.com`, `detail.tmall.com` chuyển khách chưa đăng nhập sang trang đăng nhập hoặc bắt giải mã
  xác minh. Một số trang 1688 xem được. Vì vậy với Taobao/Tmall, AI thường chỉ thấy tên và giá trong kết quả tìm kiếm,
  ít khi có đánh giá. Đây là nhận định của bên thứ ba; chưa tự thử.
- **Chi phí:** web search $10 / 1.000 lượt tìm, cộng tiền token; web fetch chỉ tính token. Một lần săn một đề (4 sàn) mất
  vài lượt tìm cho mỗi sàn.
  Nguồn: [Web fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool) ·
  [Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).

## Cấu hình nâng cao từng nguồn (hồ sơ đọc link và ảnh)

Mỗi thẻ sàn có mục gập **«Cấu hình nâng cao»**. Dưới các thẻ có phần **«Nguồn khác»** cho Amazon (Mỹ), Tiểu Hồng Thư và
**«Trang khác»**: hồ sơ chung cho link không thuộc sàn nào. Hồ sơ cho hệ thống biết cách nhận ra link sản phẩm của sàn,
rút gọn link, lấy ảnh cỡ lớn và tải ảnh. Mặc định viết sẵn trong code (`api/app/integrations/source_profiles.py`). Ô nào
chị sửa thì ô đó thắng mặc định, các ô khác vẫn theo mặc định. Ô đã sửa có nhãn «đã sửa» và nút «dùng mặc định».
«Khôi phục mặc định» bỏ mọi ô đã sửa của nguồn đó.

Hồ sơ được dùng ở mọi chỗ có link và ảnh:

- **kết quả tìm** (theo từ khoá, bằng ảnh): link chuẩn, mã món, ảnh cỡ lớn, bỏ ảnh lạ;
- **«Dán link lấy hồ sơ»** và **«Lấy ảnh và chi tiết»**: nhận ra sàn của link, đưa link chuẩn cho driver;
- **khử trùng**: cùng một món dán hai lần với tham số khác nhau vẫn là một ứng viên, vì khoá khử trùng là mã món;
- **lưu ảnh về kho**: chỉ tải ảnh ở máy chủ ảnh của sàn, kèm header sàn cần.

Dữ liệu từ đường «Giả lập» không bị lọc theo máy chủ ảnh, vì ảnh giữ chỗ placehold.co không nằm trên máy chủ ảnh của sàn.

| Ô | Dùng làm gì | Ví dụ (mặc định) |
|---|---|---|
| **Tên miền của sàn** | Link có tên miền này (gồm cả tên miền con) là của sàn này. | `amazon.co.jp` · `1688.com` · `tmall.com`, `tmall.hk` |
| **Mẫu link sản phẩm** | Biểu thức (regex) có nhóm `(?P<id>…)` để lấy **mã món**. Nhiều dòng thì thử lần lượt. | Amazon: `amazon\.co\.jp/(?:.*/)?(?:dp\|gp/product\|…)/(?P<id>[A-Z0-9]{10})` (ASIN) · 1688: `1688\.com/offer/(?P<id>\d{6,})\.html` · Taobao: `taobao\.com/.*[?&](?:id\|itemId)=(?P<id>\d{6,})` · Rakuten: `item\.rakuten\.co\.jp/(?P<id>cửa-hàng/món)` |
| **Link chuẩn** | Dựng lại link ngắn từ mã món, phải có `{id}`. Để trống thì giữ link gốc, chỉ bỏ tham số. | `https://www.amazon.co.jp/dp/{id}` · `https://detail.1688.com/offer/{id}.html` · `https://item.taobao.com/item.htm?id={id}` · `https://item.rakuten.co.jp/{id}/` |
| **Tham số giữ lại** | Khi không dựng link chuẩn: tham số nào được giữ. `*` là giữ mọi tham số trừ tham số theo dõi (`utm_*`, `spm`, `fbclid`…). Để trống là bỏ hết. | Tiểu Hồng Thư: `xsec_token, xsec_source` (thiếu thì trang không mở) · Trang khác: `*` |
| **Máy chủ ảnh** | Chỉ nhận ảnh ở đây: ảnh AI trả về và ảnh tải về kho. Mẫu là tên máy chủ, có thể kèm đường dẫn; `*` thay cho một đoạn bất kỳ. Để trống là nhận mọi nơi. | `*.alicdn.com` · `m.media-amazon.com/images/I/*` (bỏ logo, ảnh khung trang `/images/G/`) · `*.rakuten.co.jp`, `*.r10s.jp` |
| **Đổi link ảnh sang ảnh lớn** | Mỗi dòng `tìm => thay bằng` (regex, áp lần lượt từ trên xuống). | Amazon: `\._[A-Za-z0-9_,+-]+_\.(jpe?g\|png\|gif\|webp)$ => .\1` (`…/61SrKBHi8ML._AC_SX300_.jpg` → `…/61SrKBHi8ML.jpg`) · alicdn: `(\.(?:jpe?g\|png\|gif\|webp))_[^/]*$ => \1` (`….jpg_400x400q90.jpg_.webp` → `….jpg`) · Rakuten: `thumbnail.image.rakuten.co.jp/@0_mall/` → `image.rakuten.co.jp/`, bỏ `?_ex=128x128` |
| **Header khi tải ảnh / đọc trang** | Mỗi dòng `Tên: giá trị`. Dùng được `Referer`, `User-Agent`, `Accept-Language`, `Origin`, `Accept`. Mặc định hệ thống **không** gửi Referer. | 1688: `Referer: https://detail.1688.com/` (CDN alicdn hay đòi) · Amazon: `Accept-Language: ja-JP,ja;q=0.9` |
| **Cách đọc trang chi tiết** | «Theo cách lấy hàng» là đi đường chị chọn ở thẻ sàn (giả lập, AI, OneBound…). «Không đọc trang» là báo lỗi ngay, không gọi AI; dùng khi trang luôn bị chặn (captcha) để khỏi tốn tiền. | Mặc định «Theo cách lấy hàng» |
| **Mẫu ảnh trong trang** | Máy chủ tự đọc trang sản phẩm (không qua AI, không tốn tiền) rồi lấy ảnh theo các regex này; nhóm `(…)` đầu tiên là link ảnh. Để trống là không đọc. | Amazon: `"hiRes":"(https://m\.media-amazon\.com/images/I/[^"]+)"` |
| **Dặn thêm AI** | Vài dòng thêm vào lời dặn AI khi tìm hoặc đọc trang của sàn này: ảnh nằm ở đâu, giá nào là giá thật. | Amazon: «giá thật ở khối mua, không lấy giá mục 一緒に購入» |
| **Số ảnh tối đa** | Số ảnh giữ cho mỗi món, từ 1 đến 12. | 12 |

**«Thử với một link»** (trong mục nâng cao): chị dán link sản phẩm, có thể thêm một link ảnh, rồi bấm «Thử». Kết quả
gồm nguồn nhận ra, mã món, link chuẩn, link ảnh sau khi đổi và ảnh có thuộc máy chủ ảnh hay không. Nếu chị đang sửa dở
thì hệ thống thử theo bản đang sửa (chưa cần lưu). Phần thử chỉ tính trên máy chủ: không gọi AI, không mở trang.

**Khi lưu, hệ thống kiểm:** regex phải dịch được; «Mẫu link sản phẩm» phải có nhóm `(?P<id>…)`; «Link chuẩn» phải bắt
đầu bằng `https://` và chỉ dùng `{id}`; «thay bằng» không được nhắc tới nhóm không có (`\2` khi chỉ có một nhóm); header
chỉ nhận tên trong danh sách trên và không được xuống dòng. Sai thì hiện câu báo lỗi và không lưu gì.

**Amazon Nhật (chạy thật 26/11/2026).** Có ba nguyên nhân. (1) Link Amazon chứa nguyên tên món tiếng Nhật đã mã hoá
(`%E3%83%98…`), dài hơn 250 ký tự là giới hạn của web_fetch; nay hệ thống tự rút gọn thành
`https://www.amazon.co.jp/dp/<ASIN>`. (2) web_fetch chỉ mở link «đã có trong cuộc trò chuyện». Link nằm trong JSON liền
(`{"url":"…"}`) không được nhận ra, nên lỗi `url_not_in_prior_context` xảy ra với **mọi sàn**. Nay link được gửi AI trên
một dòng riêng (`url: …`). (3) Kể cả khi link hợp lệ, web_fetch vẫn **từ chối amazon.co.jp** (`url_not_allowed`): AI
không đọc được trang Amazon. Vì vậy ảnh Amazon lấy theo «Mẫu ảnh trong trang»: máy chủ tự đọc trang và lấy các ảnh
`hiRes`, không tốn tiền AI. Cách này chạy được từ máy dev, chưa kiểm từ IP máy chủ thật (Amazon có thể bắt captcha). Thông
số, giá và đánh giá Amazon vẫn chỉ lấy được từ đoạn trích trong kết quả tìm kiếm. Trang 1688 trả trang captcha
(`_____tmd_____/punish`) cho web_fetch → dùng nút «Gửi sang Hàng Chọn» (mục dưới).

## Nút «Gửi sang Hàng Chọn»

Dùng khi máy chủ không đọc được trang (1688 bắt captcha, Taobao/Tmall bắt đăng nhập, Amazon không cho AI đọc): chị mở
trang món trên trình duyệt **máy tính** đã đăng nhập sàn, bấm nút trên thanh dấu trang, trình duyệt của chị đọc trang và
gửi sang. Không tốn lượt AI đọc trang; chỉ tốn một lượt dịch như «Dán link».

**Cài một lần:** *Cài đặt → Nguồn hàng* → thẻ «Nút Gửi sang Hàng Chọn» → kéo nút lên thanh dấu trang (Chrome: bật thanh
dấu trang bằng ⌘⇧B). Ở *Săn hàng*, menu «⋯» có lối tắt tới thẻ này. **Dùng:** mở trang món → bấm nút → cửa sổ nhỏ hiện tên,
giá, ảnh, số thông số → «Cập nhật ứng viên» (đã có món cùng sàn + mã: mã offer 1688, id Taobao/Tmall, ASIN, mã Rakuten; trang
lạ thì cùng link) hoặc chọn đề rồi «Thêm vào đề» / «Thêm ứng viên lẻ». Chưa đăng nhập bàn làm việc thì cửa sổ mời đăng nhập
rồi quay lại, dữ liệu vẫn giữ.

| Trang | Đọc được (khi trang có) |
|---|---|
| 1688 | tên, giá, ảnh chính (cbu01.alicdn.com, bỏ đuôi cỡ), thông số (bảng thuộc tính + `featureAttributes`), phân loại (`skuProps`), tên/link xưởng, số đã bán, số lượng tối thiểu, điểm sao |
| Taobao, Tmall | tên, giá, ảnh thu nhỏ → ảnh gốc, thông số, phân loại, cửa hàng, «已售» |
| Amazon Nhật / Mỹ | tên (`#productTitle`), giá khối mua, ảnh `hiRes` / `data-a-dynamic-image`, sao, số đánh giá, «đã mua tháng trước», người bán, bảng thông số, gạch đầu dòng, phân loại |
| Rakuten | tên, giá, ảnh (bỏ `?_ex=`, `?fitin=`), cửa hàng (theo đường dẫn), sao, số đánh giá, bảng thông số |
| Trang bất kỳ | JSON-LD `Product` (tên, ảnh, giá, tiền tệ, sao, đánh giá, thương hiệu), `og:*`, thêm ảnh to nhất đang hiện |

**Cách chạy (cho người cài máy chủ).** Mã đọc trang nằm trọn trong nút (`web/src/lib/clipper/extract.ts`, dựng bằng
`clipPage.toString()`), không tải script từ ngoài vì CSP của sàn hay chặn script lạ. Dữ liệu đi sang cửa sổ
`/desk/kep` ở phần `#` của link (không qua máy chủ nào trước khi chị bấm lưu); không dùng `postMessage` vì sàn đặt
Cross-Origin-Opener-Policy thì liên hệ giữa hai cửa sổ bị cắt. Cửa sổ cùng origin với bàn làm việc nên gọi API bằng phiên
sẵn có (cookie SameSite=Lax; trang khác không gửi kèm được). `GET /api/desk/sourcing/clip/match?url=` (món đã có chưa),
`POST /api/desk/sourcing/clip` (chị và người phụ): kiểm cỡ từng trường, link trang/ảnh/người bán chỉ nhận https, ≤ 40 link
ảnh; ảnh qua hồ sơ nguồn (đổi cỡ lớn, chỉ máy chủ ảnh của sàn, ≤ 12) và tải về kho như «Lấy ảnh và chi tiết». Lượt là
`link_import` có `input.clip`, ghi qua action `sourcing.import_link` (nhật ký AI «Nhận hồ sơ từ trang chị mở»); món đã có
thì cập nhật số liệu mới, giữ tên tiếng Việt, điểm, giai đoạn, đề; `raw.clip` giữ nguyên bản gửi; trạng thái «Lấy ảnh và
chi tiết» thành «xong» (xoá lỗi cũ). Khi «Lấy ảnh và chi tiết» không đọc được trang, trạng thái có `blocked` → hồ sơ hiện
«Mở trang nguồn».

**Giới hạn:** sàn đổi giao diện thì bộ đọc có thể sót trường (nhất là Taobao/Tmall: tên class có hậu tố băm, chọn theo
tiền tố); trường nào không thấy thì để trống, không đoán; giá nhiều bậc lấy số đầu tiên thấy. Ảnh trong phần mô tả chi tiết
(1688/Taobao tải chậm khi cuộn) không lấy. Điện thoại khó dùng bookmarklet. Một trang bất kỳ có thể tự mở
`/desk/kep#…` với dữ liệu giả; chị vẫn phải bấm lưu, và dữ liệu chỉ thành một ứng viên.

## Lưu trữ và an toàn (cho người cài máy chủ)

- Cấu hình nâng cao: `app_settings` khoá `source_profile.<sàn>` = `{"fields": {ô: giá trị}}` (chỉ ô đã sửa; khôi phục
  mặc định là xoá dòng). Không hiện ở `GET /api/desk/control/settings`, và `PATCH /settings/{key}` từ chối. Lưu vết
  `control.source_profile_saved` (tên ô đã đổi). Điểm cuối (chỉ owner): `PATCH /api/desk/control/sources/profiles/{sàn}`
  (`{"fields": {ô: giá trị | null}}`, `null` là về mặc định) · `DELETE …/profiles/{sàn}` · `POST …/profiles/try`
  (`{url, image_url?, platform?, fields?}`). Hồ sơ hiệu lực nằm ở `profiles` của `GET /api/desk/control/sources`.
- Tải link bên ngoài (ảnh, trang sản phẩm) đi qua `app/integrations/safe_http.py`. Bước phân giải tên miền và kiểm IP
  chạy ngay lúc mở kết nối, và kết nối đi thẳng tới IP vừa kiểm (chống DNS rebinding). TLS vẫn kiểm theo tên miền gốc.
  Mỗi lần chuyển hướng (tối đa 3) được kiểm lại.
- Lưu ở bảng `app_settings`. Lựa chọn từng sàn nằm ở `source_account.routes` = `{"routes": {sàn: driver}}`; khoá của
  từng dịch vụ nằm ở `source_account.onebound` và `source_account.rakuten`, cùng dạng JSON với `channel_account.*`. Ô bí
  mật mã hoá Fernet bằng `SECRETS_ENCRYPTION_KEY`. API chỉ trả 4 ký tự cuối. Các dòng này không hiện trong
  `GET /api/desk/control/settings` và `PATCH /settings/{key}` từ chối chúng.
- Thứ tự ưu tiên là **Cài đặt > biến môi trường**: `ONEBOUND_API_KEY`, `ONEBOUND_API_SECRET`, `RAKUTEN_APPLICATION_ID`,
  `RAKUTEN_ACCESS_KEY`, `SOURCES_DRIVER`. API đọc lại cấu hình sau mỗi lần lưu; worker đọc lại ở đầu mỗi job (cùng nhịp
  với cấu hình kênh, chậm nhất 5 giây).
- Lưu vết: `control.source_route_saved`, `control.source_account_saved` (chỉ ghi tên ô) và
  `control.source_account_checked`. Câu báo lỗi của dịch vụ được lọc khoá trước khi hiện và trước khi lưu.
- Điểm cuối (chỉ owner): `GET /api/desk/control/sources`, `PATCH /api/desk/control/sources/platforms/{sàn}`
  (`{"driver": "mock"|"web"|"onebound"|"rakuten"|null}`), `PATCH /api/desk/control/sources/accounts/{dịch vụ}`,
  `POST /api/desk/control/sources/accounts/{dịch vụ}/check`.
