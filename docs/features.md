# Danh mục chức năng

Nguồn: bản thiết kế `docs/design/ban-thiet-ke.html` (mở bằng trình duyệt để xem wireframe). Anh Cường đã chọn **Làm ngay** cho cả 73 chức năng (25/11/2026).

Mức tự động: **AI tự làm** (ghi nhật ký, hoàn tác được) · **AI làm, chị duyệt** (qua hàng chờ duyệt) · **Chị quyết** (AI chỉ hỗ trợ). GĐ = giai đoạn đề xuất ban đầu, dùng làm thứ tự ưu tiên.

## Săn hàng

Tìm sản phẩm theo đúng ý chị, từ nhiều nguồn, bằng nhiều thứ tiếng.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| a1 | Ra đề bằng lời | Chị quyết | 1 | Chị nói hoặc gõ tiêu chí như đang dặn một người giúp việc. AI chuyển thành bộ lọc và cho chị xem nó hiểu thế nào. |
| a2 | Dán link, lấy hồ sơ | AI tự làm | 1 | Dán link một sản phẩm bất kỳ. AI lấy giá, ảnh, thông số, đánh giá và dịch sang tiếng Việt. |
| a3 | Tìm bằng ảnh | AI tự làm | 1 | Chị chụp một món thấy ngoài đời hoặc trên mạng. AI tìm đúng mẫu và các xưởng bán cùng mẫu. |
| a4 | Quét nhiều nguồn | AI tự làm | 1 | AI tìm trên 1688, Taobao, Rakuten, Amazon Nhật bằng từ khoá đã dịch, gom về một danh sách ứng viên. |
| a5 | Radar xu hướng | AI tự làm | 2 | Mỗi sáng AI báo vài món đang lên ở Tiểu Hồng Thư, @cosme, TikTok Shop Việt Nam, kèm lý do đáng xem. |
| a6 | Nghe khách muốn gì | AI tự làm | 2 | AI gom câu hỏi và lời nhờ tìm của khách thành danh sách nhu cầu, xếp theo số người hỏi. |
| a7 | Săn theo lịch | AI tự làm | 3 | Đề tìm kiếm đã lưu chạy lại hằng tuần, chỉ báo khi có ứng viên mới đạt ngưỡng. |

## Thẩm định và so sánh

Biến hàng trăm trang sản phẩm thành một hồ sơ chị đọc trong hai phút.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| b1 | Hồ sơ thẩm định | AI tự làm | 1 | Một trang cho mỗi ứng viên: thông số, ảnh thật từ người mua, giá ở các nơi, điểm mạnh và yếu. |
| b2 | Đọc hộ đánh giá | AI tự làm | 1 | AI đọc hàng trăm đánh giá tiếng Trung, tiếng Nhật, tóm tắt lời khen chê lặp lại, tách riêng đánh giá 1–2 sao. |
| b3 | Bảng so sánh cạnh nhau | AI tự làm | 1 | Xếp 3–5 ứng viên cùng loại theo đúng các tiêu chí chị quan tâm. |
| b4 | Chấm điểm theo khung của chị | AI làm, chị duyệt | 1 | Bảy tiêu chí, trọng số chị đặt. AI chấm nháp và nêu căn cứ, chị sửa điểm. |
| b5 | Giá bán ở Việt Nam | AI tự làm | 1 | AI tìm giá cùng món trên Shopee, TikTok Shop để biết còn chỗ cho mình không. |
| b6 | Kiểm an toàn và giấy tờ | AI làm, chị duyệt | 2 | Soát thành phần, chất liệu, hàng có pin hay chất lỏng, có thuộc nhóm phải công bố không. |
| b7 | Cảnh báo hàng nhái, đánh giá ảo | AI tự làm | 2 | So ảnh và giá giữa các shop, phát hiện đánh giá bất thường. |

## Bàn chọn

Phần của chị. Hệ thống chỉ ghi lại và sắp xếp.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| c1 | Bảng chọn | Chị quyết | 1 | Ứng viên, Mua mẫu, Đang thử, Đã chọn, Đã loại. Chị chuyển món qua từng cột. |
| c2 | Nhật ký thử hàng bằng giọng nói | Chị quyết | 1 | Chị nói vài câu và chụp ảnh trong lúc dùng. AI chép lại và xếp vào đúng món. |
| c3 | Lý do chọn và điều chưa ưng | AI làm, chị duyệt | 1 | Từ ghi chú của chị, AI soạn hai đoạn này cho trang sản phẩm. Chị sửa lời. |
| c4 | Lý do loại | Chị quyết | 1 | Ghi vì sao loại từng ứng viên. Thành dữ liệu cho trang Hồ sơ chọn. |
| c5 | Bộ nguyên tắc của chị | Chị quyết | 2 | Lưu nguyên tắc chọn theo từng nhóm hàng để AI lọc từ đầu. |
| c6 | AI học gu chị | AI tự làm | 3 | Sau mỗi lần chọn hoặc loại, AI chỉnh cách xếp hạng ứng viên cho giống mắt chị hơn. |

## Nguồn cung và giá vốn

Từ lúc hỏi giá tới lúc hàng về tới nhà.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| d1 | Sổ nhà cung cấp | AI tự làm | 1 | Mỗi shop hoặc xưởng một hồ sơ: điểm uy tín, lịch sử đặt, tỉ lệ lỗi. |
| d2 | Tính giá vốn về tay | AI tự làm | 1 | Giá gốc, tỷ giá, phí mua hộ, cước, thuế, hao hụt. Tự cập nhật khi tỷ giá hoặc cước đổi. |
| d3 | Đề xuất giá bán | AI làm, chị duyệt | 1 | AI đề xuất giá theo giá vốn, giá thị trường và biên lợi nhuận chị đặt. |
| d4 | Chứng từ nguồn gốc | AI tự làm | 1 | Lưu hoá đơn, tờ khai, ảnh nhãn gốc theo từng lô hàng. |
| d5 | Đặt mẫu, đặt lô | AI làm, chị duyệt | 2 | AI soạn đơn cho đơn vị mua hộ hoặc nhà cung cấp, chị duyệt rồi mới gửi. |
| d6 | Nhắn hỏi nhà cung cấp | AI làm, chị duyệt | 2 | AI soạn tin tiếng Trung, tiếng Nhật hỏi giá, số lượng tối thiểu, thời gian; dịch câu trả lời. |
| d7 | Theo dõi lô hàng về | AI tự làm | 2 | Các mốc: đã đặt, về kho bên bán, thông quan, về nhà. |

## Website Hàng Chọn

Nơi khách đọc kỹ, đặt hàng và theo dõi đơn.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| e1 | Tự dựng trang sản phẩm | AI làm, chị duyệt | 1 | Từ hồ sơ đã chọn, AI viết tên, mô tả, thông số, phần hỏi đáp. Chị duyệt rồi đăng. |
| e2 | Con dấu và hồ sơ chọn | AI tự làm | 1 | Mỗi món hiện tỉ lệ chọn, thời gian thử, lý do chọn, điều chưa ưng và các món đã loại. |
| e3 | Mở bán theo đợt | AI làm, chị duyệt | 1 | Đợt gom đơn có hạn chót, số suất, ngày hàng về dự kiến. |
| e4 | Đặt hàng một trang | AI tự làm | 1 | Không cần tạo tài khoản. Chuyển khoản bằng mã QR tự xác nhận, hoặc trả tiền khi nhận. |
| e5 | Theo dõi đơn | AI tự làm | 1 | Khách xem hành trình đơn bằng số điện thoại và mã đơn. |
| e6 | Xử lý ảnh sản phẩm | AI tự làm | 1 | Ảnh thật chị chụp là chính. AI cắt, cân sáng, làm sạch nền; không tạo ảnh giả. |
| e7 | Trợ lý hỏi đáp trên web | AI tự làm | 2 | Trả lời từ hồ sơ thẩm định, có dẫn nguồn. Không biết thì nói không biết và chuyển chị. |
| e8 | Đánh giá có ảnh của khách | AI làm, chị duyệt | 2 | Tự xin đánh giá sau khi khách nhận hàng. AI lọc, chị duyệt hiển thị. |
| e9 | Trang Nhờ chị tìm | AI tự làm | 2 | Khách gửi nhu cầu, người khác bấm cùng cần. Đủ số người thì mở tìm. |
| e10 | Để AI đọc được | AI tự làm | 2 | Dữ liệu sản phẩm có cấu trúc và nguồn cấp cho Google, sẵn sàng cho các trợ lý mua sắm AI. |

## Xưởng nội dung và đăng bài

Từ một hồ sơ chọn ra bài cho mọi kênh.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| f1 | Một sản phẩm, nhiều bản | AI làm, chị duyệt | 1 | AI soạn bài Facebook, bộ ảnh Instagram, kịch bản TikTok, tin Zalo. Mỗi kênh một cách viết. |
| f2 | Giọng của chị | AI tự làm | 1 | AI học cách viết từ bài cũ và ghi âm của chị để bài mới nghe giống chị. |
| f3 | Lịch đăng | AI làm, chị duyệt | 1 | AI xếp lịch tuần, chị đổi chỗ khi cần. |
| f4 | Đăng tự động | AI tự làm | 1 | Facebook, Instagram, Threads đăng thẳng. TikTok đẩy bản nháp vào app để chị bấm đăng. |
| f5 | Soát lời quảng cáo | AI tự làm | 1 | Kiểm câu chữ: đúng số liệu trong hồ sơ, không nói quá công dụng, gắn nhãn khi có phần do AI tạo. |
| f6 | Dựng video ngắn | AI làm, chị duyệt | 2 | Từ clip chị quay khi thử hàng, AI cắt, chèn phụ đề, gợi ý nhạc. |
| f7 | Đo và học | AI tự làm | 2 | Bài nào ra đơn; AI rút ra kiểu bài nên làm tiếp. |
| f8 | Kịch bản livestream | AI làm, chị duyệt | 3 | Dàn ý, thứ tự món, câu khách hay hỏi. Chị là người lên hình. |

## Đơn hàng và vận hành

Từ lúc khách bấm đặt tới lúc nhận hàng.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| g1 | Gom đơn mọi kênh | AI tự làm | 1 | Đơn từ web, bình luận, tin nhắn về một danh sách. |
| g2 | Khớp thanh toán | AI tự làm | 1 | Tự khớp khoản chuyển tới với đơn, báo khách ngay. |
| g3 | Tổng hợp đợt để đặt nguồn | AI làm, chị duyệt | 1 | Hết đợt, AI cộng số lượng và soạn đơn đặt nhà cung cấp. Chị duyệt. |
| g4 | Tạo vận đơn | AI tự làm | 1 | Chọn hãng theo phí và thời gian, in nhãn. |
| g5 | Báo tin cho khách | AI tự làm | 1 | Tự nhắn các mốc: đã nhận đơn, hàng đang về, đang giao. |
| g6 | Chốt đơn từ tin nhắn | AI làm, chị duyệt | 2 | AI nhận ra khách muốn mua, hỏi đủ thông tin, tạo đơn nháp. |
| g7 | Đổi trả, hoàn tiền | Chị quyết | 2 | AI kiểm điều kiện, soạn phương án. Chị quyết. |
| g8 | Tồn kho nhỏ | AI tự làm | 2 | Số lượng các món giữ sẵn, báo khi sắp hết. |
| g9 | Bán trên TikTok Shop, Shopee | AI tự làm | 3 | Đồng bộ sản phẩm và đơn khi được cấp quyền API. |

## Chăm khách và cộng đồng

Trả lời nhanh, nhớ từng khách, giữ khách ở lại.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| h1 | Hộp thư gộp | AI tự làm | 1 | Bình luận và tin nhắn Facebook, Instagram, Zalo ở một chỗ. |
| h2 | AI soạn sẵn câu trả lời | AI làm, chị duyệt | 1 | Câu về giá, còn hàng, phí giao thì AI trả lời ngay. Câu khác AI soạn nháp chờ chị. |
| h3 | Chuyển cho chị | Chị quyết | 1 | Khiếu nại, hàng lỗi, câu hỏi về sức khoẻ: AI không tự trả lời. |
| h4 | Sổ khách | AI tự làm | 1 | Mỗi khách: đã mua gì, hỏi gì, quan tâm gì. |
| h5 | Nhóm khách quen | AI làm, chị duyệt | 2 | Nhóm Zalo kín. AI soạn tin báo đợt mới và tóm tắt thảo luận trong nhóm. |
| h6 | Nhắc mua lại đúng lúc | AI làm, chị duyệt | 2 | Món tiêu hao sắp hết thì nhắc đúng người. Không nhắn đại trà. |
| h7 | Giới thiệu bạn | AI tự làm | 3 | Mã giới thiệu, quà cho cả hai. Đo trước rồi mới mở rộng. |
| h8 | Khách thử hàng cùng chị | Chị quyết | 3 | Mời vài khách quen dùng thử mẫu trước khi chị quyết định chọn. |

## Trung tâm điều khiển

Nơi chị giám sát và can thiệp.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| i1 | Hôm nay | AI tự làm | 1 | Một màn hình: việc chờ chị, việc AI đã làm, số đơn, tiền về. |
| i2 | Hàng chờ duyệt | Chị quyết | 1 | Mọi thứ AI làm xong mà cần chị gật: duyệt, sửa, hoặc trả lại kèm lời nhắn. |
| i3 | Mức tự chủ theo từng việc | Chị quyết | 1 | Chị đặt việc nào AI tự làm, việc nào phải hỏi. Nới dần khi đã tin. |
| i4 | Nhật ký AI | AI tự làm | 1 | Xem AI đã làm gì, dựa vào đâu. Hoàn tác được. |
| i5 | Báo cáo tuần | AI tự làm | 2 | Doanh thu, biên lợi nhuận từng món, khách quay lại, bài hiệu quả. |
| i6 | Ra lệnh bằng lời | AI tự làm | 2 | Nói một câu từ bất kỳ màn hình nào để giao việc cho AI. |

## Nền tảng

Những việc không ai thấy nhưng phải có.

| Mã | Chức năng | Mức | GĐ | Mô tả |
|---|---|---|---|---|
| k1 | Sổ doanh thu, chi phí | AI tự làm | 1 | Ghi tự động từng đơn, xuất bảng kê phục vụ khai thuế. |
| k2 | Trần chi phí AI | AI tự làm | 1 | Theo dõi tiền AI theo tháng. Chạm trần thì dừng và hỏi chị. |
| k3 | Nhãn AI và lưu vết | AI tự làm | 1 | Tự gắn nhãn nội dung do AI tạo. Lưu ai duyệt gì, lúc nào. |
| k4 | Sao lưu và phân quyền | AI tự làm | 2 | Sao lưu hằng ngày. Tài khoản phụ cho người phụ giúp. |
| k5 | Hoá đơn điện tử | AI tự làm | 3 | Nối với nhà cung cấp hoá đơn điện tử khi cần. |
