# Sổ trạng thái chức năng

Cập nhật 27/11/2026 (website: khẩu hiệu bốn mục menu, «Của tôi» gộp giỏ + đơn với đăng nhập bằng mã một lần, bỏ «Người chọn» khỏi menu; thêm «Ghi chú dùng thử» trên website, «Mời thử cùng»); 26/11/2026 (thêm Cài đặt → Mạng xã hội, Cài đặt → Nguồn hàng); 25/11/2026 (chiều), sau đợt rà đối chiếu thiết kế và 4 lát cắt bù phần thiếu (`feat/gu-chon`, `feat/don-khach`, `feat/nguon-noidung`, `feat/dieu-khien`). Danh mục gốc: [features.md](features.md).

**Cách đọc cột «Trạng thái»** (chỉ ghi «chạy thật» cho thứ đã tự thấy chạy — trong bài test tích hợp
`api/tests/integration/test_lifecycle.py`, bài Playwright `web/e2e/lifecycle.spec.ts`, bài rà route `web/e2e/routes.spec.ts`
hoặc mở tay trên máy dev với dữ liệu mẫu `uv run python -m app.seed --demo`):

- **chạy thật** — logic của chính hệ thống, không cần tài khoản ngoài; đã chạy từ giao diện tới CSDL.
- **chạy với AI giả** — luồng chạy trọn với provider `fake` trong test/e2e. Từ 25/11 máy chạy thử đã nối **Anthropic
  thật** (khoá nhập ở Cài đặt → AI, mã hoá); các tác vụ AI chạy thật được nhưng **chất lượng từng tác vụ chưa đo**.
- **chạy với mock, cần tài khoản X** — luồng chạy trọn với driver `mock`; driver thật đã viết theo tài liệu chính thức
  nhưng **chưa thử với tài khoản thật**.
- **một phần — thiếu gì** — nói rõ phần thiếu.

| Mã | Chức năng | Trạng thái | Màn hình |
|---|---|---|---|
| a1 | Ra đề bằng lời | chạy với AI giả, cần khoá Anthropic (nói bằng giọng dùng Web Speech của trình duyệt) | `/desk/san-hang`, `/desk/san-hang/de/[id]` |
| a2 | Dán link, lấy hồ sơ | chạy với mock; chọn đường từng sàn ở *Cài đặt → Nguồn hàng*: AI tìm trên web (cần AI thật), OneBound (1688/Taobao/Tmall) hoặc Rakuten API — driver thật chưa thử với khoá thật | `/desk/san-hang` |
| a3 | Tìm bằng ảnh | chạy với mock, cần tài khoản OneBound (hoặc AI tìm trên web) | `/desk/san-hang` |
| a4 | Quét nhiều nguồn | chạy với mock; mỗi sàn đi đường chị chọn ở *Cài đặt → Nguồn hàng* (OneBound, Rakuten API, AI tìm trên web) | `/desk/san-hang/de/[id]` |
| a5 | Radar xu hướng | chạy với mock, cần khoá Anthropic (web search) | `/desk/san-hang` |
| a6 | Nghe khách muốn gì | chạy với AI giả (gom từ tin nhắn, «Nhờ tìm», trợ lý web) | `/desk/san-hang` (nhu cầu) |
| a7 | Săn theo lịch | chạy thật phần lịch (cron 7 ngày, ngưỡng báo); quét bằng mock | `/desk/san-hang/de/[id]` |
| b1 | Hồ sơ thẩm định | chạy với AI giả + nguồn mock, cần khoá Anthropic | `/desk/san-hang/ung-vien/[id]` |
| b2 | Đọc hộ đánh giá | chạy với AI giả + nguồn mock | `/desk/san-hang/ung-vien/[id]` |
| b3 | Bảng so sánh cạnh nhau | chạy với AI giả | `/desk/san-hang/so-sanh/[id]` |
| b4 | Chấm điểm theo khung của chị | chạy thật phần khung + chị sửa điểm (25/20/15/15/10/10/5); điểm nháp bằng AI giả | `/desk/san-hang/khung-cham`, hồ sơ thẩm định |
| b5 | Giá bán ở Việt Nam | chạy với mock (giá Shopee/TikTok giả lập), cần khoá Anthropic có web search | hồ sơ thẩm định |
| b6 | Kiểm an toàn và giấy tờ | chạy với AI giả; chị xác nhận chạy thật | hồ sơ thẩm định |
| b7 | Cảnh báo hàng nhái, đánh giá ảo | chạy với AI giả + nguồn mock; so ảnh theo hình (dHash, lệch ≤ 6 bit) giữa các shop và ứng viên — tắt khi chạy giả lập nên **chưa thử với ảnh thật** | hồ sơ thẩm định |
| c1 | Bảng chọn | chạy thật (5 cột, kéo thả trên máy tính, tab trên điện thoại); 27/11: mỗi cột cuộn riêng (tên cột + số luôn hiện, danh sách cao tối đa `100dvh − 15rem`), kéo thẻ tới gần mép trên/dưới thì cột tự cuộn; mỗi cột vẽ trước 30 thẻ, nút «Xem thêm (n)» vẽ thêm 30 (cả tab điện thoại). Máy chủ giữ trần sẵn có 200 thẻ mỗi cột (`BOARD_LIMIT`, số đếm vẫn là tổng thật); vượt trần thì cuối cột ghi «Còn n món cũ hơn chưa hiện». 27/11: ô xếp thẻ ở hàng nút đầu trang, dùng chung mọi cột và tab điện thoại: «Tự xếp» (mặc định, thứ tự chị kéo `board_position`), «Mới nhất», «Cũ nhất» (theo lúc thẻ vào cột hiện tại `stage_changed_at`, chưa chuyển cột lần nào thì lúc tìm thấy `created_at`); máy chủ xếp (`GET /board?sort=manual\|newest\|oldest`) nên trần 200 lấy đúng phần đầu; xếp theo thời gian không ghi đè thứ tự tự xếp. Khi xếp theo thời gian, kéo sang cột khác vẫn được (không ghi vị trí), thả trong cùng cột thì thông báo kèm nút «Chuyển sang Tự xếp». Nhớ lựa chọn trên từng máy (localStorage) và trên URL `?xep=moi\|cu` | `/desk/ban-chon` |
| c2 | Nhật ký thử hàng bằng giọng nói | chạy thật phần ghi/ảnh/ghi âm; chép lời bằng Web Speech; AI sắp ý bằng AI giả | `/desk/ban-chon/[id]` |
| c2, e2 | Ghi chú dùng thử trên website (27/11) | chạy thật: mỗi ghi chú của chị có công tắc «Đưa lên website» ở Bàn chọn; bản cho website là `public_text` (mặc định lời gốc đổi «chị» → «mình», chị sửa được, lời gốc giữ nguyên); «Kèm ảnh» chép ảnh ghi chú sang bản công khai qua đường xử lý ảnh (bỏ EXIF/vị trí chụp), bỏ tích thì gỡ. Soát lời bằng luật f5 (nói quá, kể quá trình chọn / mẫu bị loại, gọi «chị») + luật so sánh («so với», «hơn hẳn»…) — chỉ báo, không chặn; chưa soát bằng AI. Trang sản phẩm có mục «Ghi chú dùng thử» sau «Vì sao khách chọn» (≤ 6 ghi chú đã tích; không có thì ẩn); API công khai `trial_notes`. Ghi chú của khách thử không tích được. Hồ sơ cho AI viết bài có `public_trial_notes` (≤ 3), bài **có thể** trích như trải nghiệm của mình, không bắt buộc | `/desk/ban-chon/[id]`, `/san-pham/[slug]` |
| c3 | Lý do chọn và điều chưa ưng | chạy với AI giả; chị sửa lời rồi chốt chạy thật | `/desk/ban-chon/[id]` |
| c4 | Lý do loại | chạy thật (lý do loại chỉ hiện ở hồ sơ chọn trong desk, không ra website — chốt 25/11); món loại cùng đề với món đã chọn có link sang hồ sơ chọn của món đó (thiếu đề thì chỉ hiện lý do loại) | `/desk/ban-chon/[id]` |
| c5 | Bộ nguyên tắc của chị | chạy thật; nguyên tắc «không chọn» khớp chữ → trừ 30 điểm, gắn cờ «Trái nguyên tắc», xếp cuối (không xoá); «nên tránh» trừ 10 | `/desk/ban-chon/nguyen-tac` |
| c6 | AI học gu chị | chạy với AI giả phần học gu; gu đã học cộng/trừ điểm xếp hạng ứng viên (tối đa ±15), hiện lý do «Điểm AI 70 → 40» ở dòng ứng viên và hồ sơ | `/desk/ban-chon/gu` |
| d1 | Sổ nhà cung cấp | chạy thật; đổi bậc uy tín NCC thì ghi nhật ký AI | `/desk/nguon-cung`, `/desk/nguon-cung/ncc/[id]` |
| d2 | Tính giá vốn về tay | chạy thật (tỷ giá, cước, phí, thuế, hao hụt; tính lại hằng ngày); đổi ≥ 2% thì ghi nhật ký AI, hoàn tác về số cũ | `/desk/nguon-cung/gia-von/[id]` |
| d3 | Đề xuất giá bán | chạy thật (theo giá vốn + giá thị trường + biên chị đặt), duyệt qua hàng chờ | hàng chờ duyệt, giá vốn |
| d4 | Chứng từ nguồn gốc | chạy thật phần lưu/nhắc thiếu; AI đọc chứng từ (ảnh, PDF có chữ/ảnh nhúng) điền ô còn trống, chị sửa được — PDF quét thuần ảnh chưa đọc được; chất lượng đọc chưa thử với AI thật | `/desk/nguon-cung/don/[id]`, `/lo/[id]` |
| d5 | Đặt mẫu, đặt lô | chạy thật (luôn chờ chị); gửi cho NCC là chị tự gửi tin AI soạn | `/desk/nguon-cung/don/[id]` |
| d6 | Nhắn hỏi nhà cung cấp | chạy với AI giả (soạn/dịch); chưa gửi tự động qua WeChat/1688 | `/desk/nguon-cung/ncc/[id]` |
| d7 | Theo dõi lô hàng về | chạy thật (mốc nhập tay); tự dò qua `shipping` mock, có mốc mới thì ghi nhật ký AI | `/desk/nguon-cung/lo/[id]` |
| e1 | Tự dựng trang sản phẩm | chạy với AI giả (viết trang ở worker); chị sửa lời, AI viết lại, đăng lên website ở tab «Website» của xưởng nội dung (chạy thật, 25/11); giá và cách bán ở tab «Giá và cách bán» của `/desk/san-pham/[id]?tab=gia`, thiếu giá thì nút đăng chỉ sang đó | `/desk/noi-dung/san-pham/[id]` (tab Website), `/desk/san-pham/[id]` |
| e2 | Con dấu và hồ sơ chọn | chạy thật — website chỉ hiện con dấu «ĐÃ CHỌN» (không số n/m) + lý do chọn, không còn số liệu nào của quá trình chọn (đầu kệ, chú thích con dấu, «Về người chọn», mô tả meta, JSON-LD; API công khai bỏ `seal` và `stats`, 25/11); hồ sơ chọn đầy đủ (tỉ lệ chọn, dải số, món đã loại) chỉ ở desk: trang chi tiết món đã chọn ở Bàn chọn (25/11, kèm nút «Làm nội dung các kênh») và tab «Hồ sơ chọn» của `/desk/san-pham/[id]` (26/11) kèm dấu vết từng bước — đề săn hàng + nguồn, thẩm định + điểm + an toàn, đơn mẫu + ngày thử + ghi chú thử, quyết định (ai/lúc nào), giá vốn về tay — mỗi bước link về trang của nó (`GET /api/desk/catalog/products/{id}/selection`); link cũ `/san-pham/[slug]/ho-so-chon` chuyển hẳn (308) về trang sản phẩm | `/san-pham/[slug]`, `/desk/ban-chon/[id]`, `/desk/san-pham/[id]?tab=chon` |
| e2, f7, g1 | Hồ sơ bán của một món (26/11) | chạy thật phần đọc: tab «Hồ sơ bán» ở `/desk/san-pham/[id]?tab=ban` — nội dung Website + 5 kênh (chưa soạn / đang soạn / chờ duyệt / đã duyệt, bấm mở đúng tab xưởng `?kenh=`) → lên kênh (website, bài từng kênh, đợt, sàn) → khách (đơn, cái, đã thu, người mua lại, theo trạng thái/kênh; số liệu bài; hộp thư; trợ lý web; nhắc mở đợt; Nhờ tìm; nhắc mua lại; tồn; đánh giá). Số liệu bài và bài «đã đăng» qua driver `mock` gắn nhãn «giả lập»; sàn mock ghi «chưa nối sàn thật». Danh sách `/desk/san-pham` có cột hai chiều (chọn n/m ngày, thử bao lâu · nội dung x/6 → kênh → đơn). API `GET …/products/{id}/sales`, `GET …/products/pipeline` | `/desk/san-pham`, `/desk/san-pham/[id]?tab=ban` |
| e3 | Mở bán theo đợt | chạy thật (hẹn giờ, hết hạn/hết suất tự đóng, chốt sớm từ màn Đơn hàng) | `/dot`, `/dot/[slug]`, `/desk/san-pham/dot` |
| e4 | Đặt hàng một trang | chạy thật (COD); chuyển khoản VietQR chạy với mock, cần tài khoản SePay. 27/11: giỏ là tab đầu của «Của tôi» (mục cuối menu, biểu tượng xe đẩy kèm số món); nút giỏ riêng ở đầu trang bỏ; `/gio-hang` chuyển hẳn (308) về `/cua-toi` | `/cua-toi`, `/dat-hang` |
| e5 | Theo dõi đơn | chạy thật. 27/11: «Của tôi» → «Đơn của tôi» (`/cua-toi?tab=don`; `/don` chuyển hẳn về đây, link theo dõi `/don/[code]` giữ nguyên): chưa đăng nhập thì có đơn đặt trên máy này (localStorage, như trước), đăng nhập bằng mã một lần và tra một đơn bằng SĐT + mã đơn; đăng nhập rồi thì thấy mọi đơn của mình (đăng xuất được). Đăng nhập khách: nhập SĐT hoặc email → mã 6 chữ số qua `notify` (chỉ gửi cho liên hệ đã có đơn/hồ sơ, câu trả lời như nhau với mọi liên hệ), băm HMAC, hết hạn 10 phút, sai 5 lần bỏ, giới hạn tần suất xin/nhập mã; cookie `hc_customer` ~90 ngày, khoá ký riêng, không vào được bàn làm việc. Đăng nhập bằng SĐT thấy đơn có hồ sơ khách mang số đó hoặc người nhận là số đó; bằng email chỉ thấy đơn của hồ sơ khách **không có SĐT** (email trong sổ khách do khách tự điền, chưa xác minh). **Chạy với mock**: mã chỉ tới khách khi có kênh thật — SĐT cần mẫu ZNS OTP `login_code` (ô `ma_dang_nhap`) trong `ZALO_ZNS_TEMPLATES`, email cần SMTP; bản dev/test hiện mã ngay trên màn hình | `/cua-toi?tab=don`, `/don/[code]` |
| e6 | Xử lý ảnh sản phẩm | chạy thật (xoay, cân sáng, cắt vuông, làm trắng nền sáng đều màu từ mép ảnh — tắt được ở cài đặt; không tách vật thể, không tạo ảnh giả; bỏ mọi siêu dữ liệu EXIF/XMP/chú thích của ảnh gốc). Chị chọn dùng lại ảnh nhà cung cấp ở tab Website («Lấy từ ảnh nhà cung cấp»): chép bản đã lưu → cùng đường xử lý, `product_images.kind=supplier` + `source_url`, nhãn «Ảnh nhà cung cấp» chỉ ở desk, website không lộ link/tên NCC (26/11) | `/desk/san-pham/[id]`, `/desk/noi-dung/san-pham/[id]` |
| a2, b1, c1, e2 | Ảnh nhà cung cấp phía chọn (26/11) | chạy thật phần lưu bản sao (`candidates.image_cache`, kho `private/sourcing/candidates/…`, tải an toàn: http/https, chặn IP nội bộ kể cả sau chuyển hướng, ≤ 5 MB, chỉ JPG/PNG/WEBP/GIF, ≤ 12 ảnh mỗi món) và thư viện ảnh (danh sách ứng viên, hồ sơ thẩm định, Bàn chọn, bảng so sánh, Sản phẩm → Hồ sơ chọn). Ảnh đến từ kết quả tìm (Rakuten/OneBound trả sẵn; `web` nhờ AI ghi ảnh chính nếu thấy), từ «Lấy ảnh và chi tiết» (job `sourcing.fetch_details`, action `sourcing.fetch_details`), từ bước thẩm định (sự kiện `candidate.details_fetched`) và tự lấy cho N món điểm cao mỗi lượt quét (cài đặt `sourcing.auto_detail_top_n`, mặc định 5; với đường `web` mỗi món ~8.000–11.000đ). 1688/Taobao qua `web` hay gặp captcha | `/desk/san-hang/ung-vien/[id]`, `/desk/ban-chon/[id]` |
| e7 | Trợ lý hỏi đáp trên web | chạy với AI giả, cần khoá Anthropic | `/hoi`, trang sản phẩm |
| e8 | Đánh giá có ảnh của khách | chạy thật phần xin/gửi/duyệt (link «Viết đánh giá» trên trang theo dõi đơn); lọc bằng AI giả; tin xin đánh giá gửi qua `notify` mock. 27/11: thêm ô «Vì sao bạn chọn món này?» (không bắt buộc, ≤ 300 chữ, `reviews.choice_reason`, migration `0003_review_choice_reason`); AI lọc cả lý do; chị thấy lý do ở màn duyệt và ẩn riêng lý do mà vẫn giữ đánh giá (`reviews.reason_public`); website hiện mục «Vì sao khách chọn» ngay sau «Vì sao mình chọn» (≤ 5 lý do của đánh giá đã duyệt, kèm tên gọi; không có thì ẩn cả mục; API công khai `customer_reasons`) | `/danh-gia/[token]`, `/desk/san-pham/danh-gia` |
| e9 | Trang Nhờ tìm | chạy thật (AI gợi ý, chị duyệt mới hiện; đủ người thì AI đề xuất mở đề, chị duyệt — mức thận trọng đã chốt 25/11) | `/nho-tim`, `/desk/san-pham/nho-tim` |
| e10 | Để AI đọc được | chạy thật (JSON-LD Product/Offer, sitemap, `/feed.xml`) | trang sản phẩm |
| f1 | Một sản phẩm, nhiều bản | chạy với AI giả — xưởng có mọi món đã chọn (cả món chưa lên website); tab đầu là Website, bài Facebook/Instagram/Threads/TikTok/Zalo AI soạn khi trang website được đăng (sự kiện `product.published`), trước đó tab các kênh báo «Đăng trang website trước»; bài nào cũng có phần «Vì sao mình chọn», không nhắc hồ sơ chọn/mẫu bị loại/số món đã thử, AI không còn nhận số món đã xem và mẫu bị loại (25/11); 27/11: hồ sơ cho AI có thêm `customer_reasons` (≤ 3 lý do chọn của khách từ đánh giá đã duyệt, chưa bị ẩn) — bài **có thể** trích 1–2 câu, ghi rõ là lời khách, trích nguyên văn, không bắt buộc; bản giả Facebook trích một câu khi có | `/desk/noi-dung/san-pham/[id]`, `/desk/noi-dung/dot/[id]` |
| f2 | Giọng của chị | chạy với AI giả; học từ bài dán, ghi chú và **giọng nói** (nút «Nói», Web Speech vi-VN) | `/desk/noi-dung/giong` |
| f3 | Lịch đăng | chạy thật (xếp, đổi giờ, huỷ); AI xếp tuần bằng AI giả | `/desk/noi-dung/lich` |
| f4 | Đăng tự động | chạy với mock, cần ứng dụng Meta (Facebook/Instagram/Threads), Zalo OA, TikTok (đẩy nháp) — chị nối và bật từng kênh ở *Cài đặt → Mạng xã hội* | `/desk/noi-dung/lich` |
| f5 | Soát lời quảng cáo | chạy thật (luật số liệu/nói quá/kể quá trình chọn) + AI giả | xưởng nội dung |
| f6 | Dựng video ngắn | một phần — dựng bằng ffmpeg trên máy (cần `ffmpeg`), kế hoạch cắt bằng AI giả; chưa thử với clip thật | `/desk/noi-dung/video` |
| f7 | Đo và học | chạy với mock (số liệu bài giả lập); đơn theo bài qua `?src=` chạy thật | `/desk/noi-dung/so-lieu` |
| f8 | Kịch bản livestream | chạy với AI giả | `/desk/noi-dung/livestream` |
| g1 | Gom đơn mọi kênh | chạy thật (web, tạo tay, nháp từ tin nhắn); đơn sàn qua mock | `/desk/don-hang` |
| g2 | Khớp thanh toán | chạy với mock, cần tài khoản SePay (webhook); khớp tự động ghi nhật ký AI, hoàn tác = bỏ khớp (chặn khi đơn đã rời kho/có vận đơn/đổi trả), sổ sách gỡ doanh thu | `/desk/don-hang/van-hanh` |
| g3 | Tổng hợp đợt để đặt nguồn | chạy thật (đóng đợt → đơn đặt lô theo NCC chờ chị duyệt) | hàng chờ duyệt, `/desk/nguon-cung` |
| g4 | Tạo vận đơn | chạy với mock, cần tài khoản GHN hoặc GHTK; tạo vận đơn ghi nhật ký AI, hoàn tác = huỷ vận đơn khi hãng chưa lấy hàng | `/desk/don-hang/[id]`, `/desk/don-hang/in-nhan` |
| g5 | Báo tin cho khách | mỗi tin ghi nhật ký AI (không hoàn tác — tin đã gửi), mức `ask` thì chờ chị duyệt; chạy với mock, cần OA Zalo + ZBS (mẫu ZNS đã duyệt) hoặc máy chủ SMTP — mốc đơn, mẫu tin, chống trùng, kênh dự phòng, gửi lại khi lỗi tạm thời chạy thật; driver `zalo_zns` (viết theo tài liệu ZBS Template Message 11/2026) và `email` (SMTP) mới kiểm bằng máy chủ giả | `/desk/don-hang/van-hanh` (mẫu tin, kênh đang bật, tin gửi lỗi) |
| g6 | Chốt đơn từ tin nhắn | chạy với AI giả (đơn nháp chờ chị) | hàng chờ duyệt, `/desk/don-hang` |
| g7 | Đổi trả, hoàn tiền | chạy thật (luôn chờ chị); AI kiểm điều kiện bằng AI giả; hoàn tiền thật phải chị chuyển tay | `/don/[code]`, `/desk/don-hang/[id]` |
| g8 | Tồn kho nhỏ | chạy thật (giữ hàng khi đã trả, trừ khi giao hãng, nhập khi lô về; nhập tồn đầu kỳ, điều chỉnh tay có lý do và lịch sử, ngưỡng báo theo từng món; báo sắp hết tự làm) | `/desk/don-hang/van-hanh` |
| g9 | Bán trên TikTok Shop, Shopee | chạy với mock, cần tài khoản TikTok Shop / Shopee Open Platform; đơn sàn có vận đơn/đã giao thì tự đẩy trạng thái lên sàn (không trùng, cron đẩy lại). Shopee viết theo tài liệu; **TikTok Shop chưa đối chiếu được tài liệu «Mark Package As Shipped»** — kiểm trước khi bật | `/desk/don-hang/van-hanh` |
| h1 | Hộp thư gộp | chạy với mock, cần ứng dụng Meta + Zalo OA (webhook; khoá nhập ở *Cài đặt → Mạng xã hội*) | `/desk/khach`, `/desk/khach/hoi-thoai/[id]` |
| h2 | AI soạn sẵn câu trả lời | chạy với AI giả | hội thoại |
| h3 | Chuyển cho chị | chạy thật (luật khiếu nại/sức khoẻ) + AI giả | hội thoại, hàng chờ |
| h4 | Sổ khách | chạy thật (hồ sơ ngay từ tin nhắn đầu); tóm tắt bằng AI giả | `/desk/khach/so-khach` |
| h5 | Nhóm khách quen | chạy với AI giả; gửi nhóm Zalo qua mock | `/desk/khach/khach-quen` |
| h6 | Nhắc mua lại đúng lúc | chạy thật phần lịch và kiểm đồng ý nhận tin (chỉ khách tích «đồng ý» khi đặt hàng, chưa từ chối; nhắn «TỪ CHỐI» là thôi nhận); tin nhắc bằng AI giả, gửi qua mock | `/desk/khach/nhac-mua-lai` |
| h7 | Giới thiệu bạn | chạy thật (mã `?ref=`; bạn mới giảm 30.000đ đơn đầu; người giới thiệu được 30.000đ trừ ở đơn kế khi đơn của bạn đã trả và đã giao; chống lạm dụng) | `/desk/khach/gioi-thieu` |
| h8 | Khách thử hàng cùng chị | chạy thật (link mời, cảm nhận hiện cạnh ghi chú thử ở Bàn chọn) | `/desk/khach/thu-hang`, `/thu-hang/[token]` |
| h8 | Mời thử cùng (27/11) | chạy thật phần sổ người dùng thử, lời mời, chọn người, tiền, cảm nhận, hoàn tiền; tin cho người dùng thử (được chọn, nhắc trước hạn 2 ngày — cron 9:10) qua `notify` mock. Sổ: khách đăng ký một lần ở `/dung-thu` (tên, SĐT/Zalo hoặc email, nhóm quan tâm, đồng ý điều kiện); hồ sơ khách khớp/tạo ở orders qua sự kiện `customer.contact_submitted`. Lời mời: chị tạo ở Bàn chọn cho món đang mua mẫu / đang thử (giá, hoàn theo số tiền hoặc %, số suất, hạn cảm nhận, mô tả, ảnh chọn từ ảnh NCC đã lưu hoặc ảnh chị chụp — chép sang bản công khai bỏ EXIF, không kèm link/tên NCC) → link riêng `/dung-thu/m/[token]` (noindex, không trong sơ đồ trang/nguồn cấp; link sai và link đã đóng cùng báo 404); người trong sổ đăng ký nhanh (liên hệ lưu trên máy của chính họ, máy chủ không trả dữ liệu cũ), người mới vào sổ cùng lúc. Chị chọn theo lịch sử (số đơn, thử cùng / gửi đủ / lỡ hạn / bỏ ngang), đủ suất thì chặn. **Tiền theo dõi tay trên dòng đăng ký** («Đã nhận tiền», «Đã gửi hàng»), không tạo đơn: món chưa là sản phẩm, đơn sẽ làm lệch doanh thu, sổ sách, hồ sơ bán — **chưa ghi vào sổ doanh thu (k1)**, cần anh/chị chốt cách ghi. Cảm nhận có cấu trúc (sao, thích, chưa ưng, giá X có mua không, ảnh không bắt buộc, nơi nhận hoàn) ở `/thu-hang/[token]`, gửi một lần, quá hạn thì từ chối; thành ghi chú thử `author=tester` ở Bàn chọn (sự kiện `tester.feedback_received`) và là căn cứ phụ cho AI soạn lý do chọn (c3, có nhãn `author`), không bao giờ ra website hay bài đăng (facts nội dung bỏ ghi chú `tester`). Gửi đủ → `control.propose("crm.cotrial_refund")` luôn hỏi chị; chị chuyển tay rồi duyệt (sửa được số tiền) = «đã hoàn»; trả lại → về «đã gửi cảm nhận», đề xuất lại được. Quá hạn → «lỡ hạn», sổ gắn loại trừ; chọn lại phải xác nhận. Migration `0004_cotrial_public_notes` | `/desk/ban-chon/[id]`, `/desk/khach/dung-thu`, `/desk/khach/dung-thu/[id]`, `/dung-thu`, `/dung-thu/m/[token]`, `/thu-hang/[token]` |
| i1 | Hôm nay | chạy thật (số liệu của mọi module) | `/desk` |
| i2 | Hàng chờ duyệt | chạy thật (duyệt / sửa rồi duyệt / trả lại, bấm tới màn hình của đối tượng) | `/desk/duyet` |
| i3 | Mức tự chủ theo từng việc | chạy thật | `/desk/tu-chu` |
| i4 | Nhật ký AI | chạy thật (hoàn tác, căn cứ, bấm tới đối tượng) | `/desk/nhat-ky-ai` |
| i5 | Báo cáo tuần | chạy thật phần số liệu; nhận xét bằng AI giả | `/desk/bao-cao` |
| i6 | Ra lệnh bằng lời | chạy với AI giả; lệnh: việc chờ duyệt, đổi mức tự chủ, đề săn hàng, soạn bài cho món, tóm tắt đơn, tìm khách, mở/đóng đợt mua chung, chi phí AI, kiểm sao lưu — lệnh đổi dữ liệu luôn vào hàng chờ | nút «Nói với AI» mọi màn |
| k1 | Sổ doanh thu, chi phí | chạy thật (doanh thu khi đơn đã trả, chi phí NCC + tiền AI hằng tháng, bảng kê CSV) | `/desk/so-sach` |
| k2 | Trần chi phí AI | chạy thật phần đếm/chặn; đổi nhà cung cấp/khoá/model/trần ngay ở Cài đặt (Anthropic, OpenRouter, AI giả). Anthropic đã gọi thật được với `claude-haiku-5-5`, `claude-opus-5-5`; OpenRouter mới kiểm bằng máy chủ giả, chưa gọi thật. Model ngoài bảng giá: OpenRouter lấy chi phí nó tự báo (`usage.cost`), provider khác tính theo giá model «việc khó» (có cảnh báo trong log) | `/desk/tu-chu/chi-phi-ai`, `/desk/cai-dat/ai` |
| k3 | Nhãn AI và lưu vết | chạy thật; lưu vết cả việc đổi khoá API / cấu hình AI (ai đổi, lúc nào, đổi trường nào — không ghi giá trị khoá) | nhật ký AI, bài đăng |
| k4 | Sao lưu và phân quyền | chạy thật phần tài khoản phụ; sao lưu chạy được khi máy có `pg_dump` hoặc container Postgres (`docker exec`), image prod có `postgresql-client-16`; chép ra S3/R2 khi điền `S3_*` (driver `s3` chưa thử thật); kiểm khôi phục (checksum + giải nén + cấu trúc, không ghi đè) | `/desk/cai-dat/sao-luu`, `/desk/cai-dat/nguoi-phu-giup` |
| f4, h1, g9 | Tài khoản kênh (26/11) | chạy thật phần lưu/che khoá, công tắc giả lập ↔ thật mà driver tuân theo, lưu vết; **chưa thử với tài khoản thật** phần «Kiểm tra kết nối», «Kết nối» (OAuth TikTok, Shopee, TikTok Shop) và tự làm mới token (TikTok, Shopee, TikTok Shop, Threads, Zalo OA) — mới kiểm bằng máy chủ giả. Zalo: chưa có OAuth, chưa lấy tên OA (tài liệu không tải lại được). Hướng dẫn từng kênh: [channel-accounts.md](channel-accounts.md) | `/desk/cai-dat/mang-xa-hoi` |
| k5 | Hoá đơn điện tử | một phần — luồng soạn/duyệt/chống trùng chạy với mock (prod từ chối phát hành bằng mock); **chưa có driver nhà cung cấp hoá đơn thật** | `/desk/so-sach` |

## Cần chị/anh cung cấp để bật driver thật

Mạng xã hội và sàn (Facebook, Instagram, Threads, TikTok, Zalo OA, Shopee, TikTok Shop): chị nhập ở *Cài đặt → Mạng xã hội*
(thắng biến môi trường; hướng dẫn từng kênh ở [channel-accounts.md](channel-accounts.md)). Nguồn hàng (cách lấy hàng từng
sàn, khoá OneBound / Rakuten): *Cài đặt → Nguồn hàng*, xem [source-accounts.md](source-accounts.md). Phần còn lại đặt vào `api/.env`
(xem `api/.env.example`).

| Việc | Cần | Biến |
|---|---|---|
| AI thật (mọi chức năng «AI giả») | Khoá Claude API hoặc OpenRouter, đặt trần chi phí tháng — nhập ở *Cài đặt → AI và khoá API* (mã hoá trong CSDL) | `SECRETS_ENCRYPTION_KEY` (bắt buộc ở prod); hoặc qua env: `AI_PROVIDER=anthropic`/`openrouter`, `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`, `AI_MONTHLY_BUDGET_VND` |
| Săn hàng 1688/Taobao/Tmall, Rakuten | *Cài đặt → Nguồn hàng* (chọn đường từng sàn + khoá). 1688/Taobao: tài khoản OneBound (key + secret, trả theo lần gọi); Rakuten: Application ID + Access key (miễn phí); sàn khác: AI tìm trên web (cần AI thật) | Hoặc env: `SOURCES_DRIVER=web`/`onebound`/`rakuten`, `ONEBOUND_API_KEY`, `ONEBOUND_API_SECRET`, `RAKUTEN_APPLICATION_ID`, `RAKUTEN_ACCESS_KEY` |
| Facebook Page, Instagram, Threads (đăng bài + hộp thư) | *Cài đặt → Mạng xã hội* hoặc env. Ứng dụng Meta đã duyệt quyền `pages_manage_posts`, `pages_messaging`, `instagram_content_publish`, `instagram_manage_messages`; Page token dài hạn; webhook trỏ về `/api/hooks/social/facebook` | `META_APP_ID`, `META_APP_SECRET`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `META_IG_USER_ID`, `META_WEBHOOK_VERIFY_TOKEN`, `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` |
| Zalo OA (tin nhắn, bài viết OA) | *Cài đặt → Mạng xã hội* hoặc env. OA đã xác thực + ứng dụng Zalo, access token OA (làm mới định kỳ), webhook `/api/hooks/social/zalo_oa` | `ZALO_APP_ID`, `ZALO_OA_ID`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_SECRET` |
| TikTok (đẩy bản nháp) | *Cài đặt → Mạng xã hội* (bấm «Kết nối TikTok», token 2 giờ tự làm mới). Ứng dụng TikTok for Developers có Login Kit + Content Posting API | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN` |
| Chuyển khoản VietQR tự khớp | Tài khoản SePay nối tài khoản ngân hàng, webhook `/api/hooks/payments/sepay` | `PAYMENTS_DRIVER=sepay`, `SEPAY_API_KEY`, `SEPAY_WEBHOOK_SECRET`, `BANK_CODE`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME` |
| Giao hàng | Tài khoản GHN (token + shop id) hoặc GHTK (token + địa chỉ lấy hàng) | `SHIPPING_DRIVER=ghn`/`ghtk`, `GHN_TOKEN`, `GHN_SHOP_ID`, `GHTK_TOKEN`, `GHTK_PICK_*` |
| Báo tin cho khách (g5) | Zalo: OA đã xác thực + ứng dụng Zalo có quyền «Gửi tin qua số điện thoại», tài khoản ZBS có số dư, các mẫu tin đã được duyệt (mỗi mốc đơn một mẫu); email: máy chủ SMTP | `NOTIFY_CHANNEL_DRIVERS=zalo_oa=zalo_zns,email=email`, `ZALO_APP_ID`, `ZALO_APP_SECRET`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_REFRESH_TOKEN`, `ZALO_ZNS_TEMPLATES`, `SMTP_*` (xem [deployment.md](deployment.md) mục 6) |
| Sàn TikTok Shop / Shopee | *Cài đặt → Mạng xã hội* (bấm «Kết nối», token tự làm mới). Tài khoản Partner, quyền API shop | `MARKETPLACES_DRIVER`, `TIKTOK_SHOP_*`, `SHOPEE_*` |
| Hoá đơn điện tử (k5) | Chọn nhà cung cấp (VNPT, Viettel, MISA…) — **driver chưa viết**, xem mục dưới | `EINVOICE_DRIVER` |
| Lưu ảnh/sao lưu trên S3/R2 | Bucket + khoá | `STORAGE_DRIVER=s3`, `S3_*` |

## Hoá đơn điện tử (k5): cần gì khi chọn nhà cung cấp

Interface `api/app/integrations/einvoice` đã đủ chỗ cắm: `issue` (phát hành, chống trùng theo mã đơn), `get_status` (trạng
thái + mã của cơ quan thuế), `download` (PDF / XML), `adjust` / `replace` (hoá đơn điều chỉnh / thay thế), `cancel`.
Khi chọn nhà cung cấp cần hỏi và ghi lại: tài liệu API + môi trường thử (sandbox) và cách cấp khoá; mẫu số / ký hiệu hoá
đơn đã đăng ký (hoá đơn có mã hay không mã của cơ quan thuế, loại dành cho hộ kinh doanh); cách ký số (chữ ký số của nhà
cung cấp hay USB token / ký từ xa); quy trình xử lý sai sót họ hỗ trợ (điều chỉnh, thay thế — còn cho huỷ không, theo quy
định hiện hành); cách tra trạng thái (gọi hỏi hay webhook) và thời gian cơ quan thuế cấp mã; tải được bản PDF/XML gốc
để lưu trữ không; khoá chống phát hành trùng phía họ; giá theo gói số hoá đơn và hạn mức gọi API.

## Kiểm chứng

- `scripts/check.sh api` — ruff + toàn bộ pytest (gồm `tests/integration/test_lifecycle.py`, `test_event_contract.py`, dữ liệu mẫu).
- `scripts/check.sh web` — typecheck + eslint + vitest; `bun run build`.
- `scripts/check.sh e2e` — tự dựng CSDL e2e + dữ liệu mẫu + API + worker + web rồi chạy toàn bộ Playwright
  (gồm `e2e/lifecycle.spec.ts` và `e2e/routes.spec.ts` rà mọi route ở 390px và 1280px).
