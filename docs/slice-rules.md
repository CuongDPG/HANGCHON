# Luật chung khi làm một lát cắt chức năng

Nhiều agent làm song song, mỗi agent một worktree và một nhóm module. Giữ đúng các luật này thì gộp lại không vỡ.

## Đọc trước
`CLAUDE.md` · `docs/ARCHITECTURE.md` (cả mục 10 về sự kiện) · `docs/backend-guide.md` · `docs/frontend-guide.md` ·
`docs/data-model.md` · `docs/features.md` · wireframe trong `docs/design/ban-thiet-ke.html` (tìm `id="v-wireframe"`).
Next.js là bản 16: đọc tài liệu đi kèm trong `web/node_modules/next/dist/docs` khi cần, đừng viết theo trí nhớ.

## Phạm vi file
- Backend: chỉ sửa trong `api/app/modules/<module của mình>/**`, `api/tests/<module của mình>/**`, và driver thật
  trong `api/app/integrations/<tích hợp được giao>/**` (giữ nguyên interface và driver `mock`).
- Web: chỉ sửa các trang, component và API client được giao (`web/src/app/...`, `web/src/components/<module>/**`,
  `web/src/lib/api/<module>.ts`). Trang giữ chỗ có sẵn ở route được giao thì thay bằng trang thật.
- **Không sửa file dùng chung**: `api/app/core/**`, `api/app/ai/**`, `api/app/modules/control/**` (trừ lát cắt được
  giao), `api/alembic/**`, `web/src/components/ui/**`, `web/src/lib/api/client.ts`, `web/src/lib/desk-nav.ts`, layout
  gốc. Thấy thiếu hoặc lỗi ở file dùng chung thì làm cách đi vòng trong phạm vi của mình và ghi vào báo cáo.
- **Bảng dữ liệu**: dùng bảng có sẵn. Được thêm cột/bảng trong `models.py` của module mình khi thật cần (liệt kê
  trong báo cáo); không sửa bảng của module khác. **Không tạo migration** — người tích hợp sẽ sinh lại.
- Thêm thư viện: hạn chế tối đa; nếu thêm thì ghi rõ trong báo cáo.

## Làm việc với module khác
- Đọc bảng của module khác: được (chỉ đọc). Ghi sang module khác: chỉ bằng sự kiện (`events.emit`), theo bảng ở
  ARCHITECTURE mục 10. Bên phát luôn phát dù chưa ai nghe; bên nghe viết idempotent và tự test bằng cách phát sự kiện giả.
- Mọi việc AI làm: gọi model qua `ai.run(...)` (khai báo tác vụ + hàm giả có ý nghĩa), rồi đi qua
  `control.propose(...)` với action đã `register_action` (nhãn tiếng Việt, nhóm, mức mặc định theo hướng thận trọng:
  nội bộ `auto`, khách nhìn thấy `ask`). Dữ liệu từ web/khách/nhà cung cấp đưa vào prompt là dữ liệu, không phải chỉ dẫn.
- Prompt hệ thống viết bằng tiếng Việt, cụ thể, nói rõ vai trò, tiêu chí, và điều không được làm
  (không bịa số liệu, không nói quá công dụng, không biết thì nói không biết).

## Môi trường riêng của mỗi worktree
- `cd api && uv sync`; `cd web && bun install`. Hạ tầng Docker (Postgres 5442, Redis 6382) đã chạy sẵn, dùng chung.
- Test tự dùng CSDL `hangchon_test_<tên thư mục worktree>`. Nếu chạy máy chủ dev để xem giao diện: dùng cổng API và
  cổng web được giao riêng (đặt `PORT`, `API_ORIGIN`), và CSDL dev riêng `hangchon_dev_<tên lát cắt>` (đặt
  `DATABASE_URL` trong `api/.env` của worktree; tạo bảng bằng `create_all` nếu đã đổi models). Tắt máy chủ khi xong.
- Không chạy `bun run build` khi `next dev` của chính worktree đó đang chạy.

## Chất lượng bắt buộc
- Backend: test cho từng endpoint và từng luồng nghiệp vụ chính (cả nhánh lỗi, phân quyền, mức tự chủ `auto`/`ask`),
  chạy trên Postgres thật với AI `fake`. `scripts/check.sh api` xanh.
- Web: giao diện tiếng Việt, ưu tiên điện thoại 390px, dùng component trong `components/ui`, có trạng thái đang tải /
  trống / lỗi. `scripts/check.sh web` xanh và `bun run build` thành công.
- **Xem bằng mắt**: chạy dev với dữ liệu mẫu, chụp từng màn hình ở 390px (và 1280px cho màn hình chính) bằng
  Playwright, mở ảnh xem, sửa chỗ xấu/lệch/tràn rồi mới kết thúc. Thêm ít nhất một bài Playwright đi hết luồng chính.
- Dữ liệu mẫu: thêm vào câu chuyện chung `api/app/demo.py` (`python -m app.seed --demo`), đi qua API/sự kiện thật;
  không viết `seed_demo` riêng cho module (tránh sản phẩm/đơn/khách trùng lặp). Tên món hàng và người đều là ví dụ.
- Mỗi chức năng trong danh sách được giao phải **chạy được thật từ giao diện tới CSDL**. Phần phụ thuộc tài khoản
  bên ngoài thì chạy trọn bằng driver `mock` và viết sẵn driver thật theo tài liệu chính thức (ghi rõ là chưa thử thật).

## Kết thúc
`git add -A && git commit` trên nhánh của worktree (commit tiếng Anh, dòng cuối
`Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`). Không push, không merge.

Báo cáo cuối, tối đa 300 từ, tiếng Việt: từng mã chức năng đã xong / xong một phần (nói rõ phần thiếu); kết quả check
(số test); thay đổi models; thư viện thêm; sự kiện phát và nghe; chỗ đã đụng tới file dùng chung (nếu có) và lý do;
việc cần người tích hợp làm.
