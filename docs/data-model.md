# Mô hình dữ liệu

Nguồn sự thật là `api/app/modules/<module>/models.py`; tài liệu này mô tả **mục đích, cột chính, quan hệ và vòng đời
trạng thái** của từng bảng để các module viết song song không giẫm chân nhau. Danh mục chức năng: [features.md](features.md).

## Quy ước chung

- **Chủ sở hữu bảng**: mỗi bảng thuộc đúng một module (cột «Module» bên dưới). Module khác chỉ **đọc** hoặc ghi
  **khoá ngoại trỏ tới** bảng đó; muốn đổi cột / thêm cột ở bảng của module khác → nêu với người tích hợp, không tự sửa.
- Khoá chính `id` UUID; `created_at`/`updated_at` timestamptz (UTC). Bảng chỉ ghi thêm (nhật ký, sự kiện) chỉ có `created_at`.
- Tiền: số nguyên VND, cột tên `*_vnd`. Ngoại tệ: `*_amount` (Numeric) + `currency` (ISO 3 chữ) + `fx_rate` (VND / 1 đơn vị).
- Enum lưu **giá trị chữ thường** dạng VARCHAR(40) (không dùng kiểu enum của Postgres) → thêm giá trị mới không cần migration.
  Enum dùng chung (`SourcePlatform`, `Channel`, `Language`, `ShippingStatus`, `Carrier`, `Actor`) ở `app/core/enums.py`.
- JSONB: danh sách mặc định `[]`, đối tượng mặc định `{}`. Hình dạng gợi ý ghi trong `comment` của cột.
- Tệp (ảnh, ghi âm, chứng từ) lưu **khoá storage** (`public/...` công khai, `private/...` cần đăng nhập), không lưu URL tuyệt đối.
- Khoá ngoại tuỳ chọn `ON DELETE SET NULL`; bảng con `ON DELETE CASCADE`. Vài khoá «trỏ ngược» tạo vòng giữa các bảng
  dùng `use_alter` (tạo bằng ALTER sau cùng): `sourcing_briefs.demand_signal_id/find_request_id`,
  `demand_signals.find_request_id/product_id`, `trend_signals.candidate_id`, `threads.order_id`.
- Liên kết tới hàng chờ duyệt: bảng có thứ AI soạn cần duyệt mang `approval_item_id`; liên kết tới lần gọi AI: `ai_run_id`.
- Cờ `ai_generated` (k3) có trên mọi nội dung AI tạo mà khách có thể thấy.

## Xương sống

```
sourcing_brief ─┬─ sourcing_run
                └─ candidate (stage: candidate → sample → trial → selected | rejected)
                     ├─ assessment (+ assessment_scores) · review_digests · market_prices · comparison_items
                     ├─ trial_notes · selection_decisions · tester_invites
                     ├─ cost_sheet → price_proposal
                     └─ product (chỉ khi selected) ─┬─ product_variants · product_images · inventory_items
                                                    ├─ drop_items ← drop → purchase_order → inbound_shipment
                                                    ├─ content_draft → scheduled_post → post_metrics
                                                    └─ reviews · marketplace_listings
customer ─┬─ orders → order_items · order_events · payments · shipments → shipment_events · returns
          ├─ customer_identities · customer_notes · customer_tags · referrals · reorder_reminders
          └─ threads → messages · reply_drafts
```

Con dấu «ĐÃ CHỌN n/m»: `m` = số `candidates` cùng `brief_id`, `n` = số ứng viên `selected` của đề đó; sản phẩm giữ
ảnh chụp ở `products.selected_count / considered_count` cho desk (hồ sơ chọn) khỏi đếm lại; website không hiện số này.

---

## control — giám sát, người dùng (i1–i4, i6, k2, k3)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `users` | Tài khoản bàn làm việc. `email` (duy nhất, chữ thường), `role` `owner` (chị) / `helper` (người phụ, k4), `is_active`, `password_hash` (argon2). |
| `autonomy_settings` | Mức tự chủ chị đã đặt cho từng `action` (khoá chính). Không có dòng = mức mặc định trong sổ đăng ký. `level`: `auto` · `ask` · `off` (`locked_ask` không lưu ở đây, đến từ sổ đăng ký). |
| `approval_items` | Hàng chờ duyệt (i2). `action`, `module`, `title`, `summary`, `payload` (đủ để thực thi), `preview` (để chị xem), `edited_payload` (phần chị sửa), `rationale`/`sources` (căn cứ), `ref_type`+`ref_id` (đối tượng liên quan), `dedupe_key`, `priority`, `decision_note` (lời nhắn khi trả lại), `result`, `error`, `attempts`, `expires_at`. Vòng đời: `pending` → `approved` (đã thực thi) · `returned` (trả lại) · `failed` (thực thi lỗi, duyệt lại được → `approved`) · `cancelled` (hệ thống huỷ) · `expired` (quá `expires_at`, job mỗi giờ). Duy nhất một `pending` cho mỗi (`action`, `dedupe_key`). |
| `ai_runs` | Mỗi lần gọi model một dòng, kể cả lỗi. `task`, `provider`, `model`, `tier`, `status` (`ok`/`error`/`refused`/`blocked`), token vào/ra/cache, `web_search_requests`, `cost_usd`, `cost_vnd`, `duration_ms`, `stop_reason`, `refusal_category`, `fallback_model`, `error_code`, `output` (kết quả đã kiểm khuôn). Tổng `cost_vnd` theo tháng (giờ VN) là căn cứ trần k2. |
| `ai_activity` | Nhật ký AI (i4): mọi việc đã **thực thi**. `mode` `auto` (AI tự làm) / `approved` (sau khi chị duyệt, kèm `approval_item_id`), `payload`, `result`, `rationale`, `sources`, `ref_type/ref_id`, `undo_data` + `undoable`, `undone_at/undone_by_id`. |
| `app_settings` | Cài đặt khoá → giá trị JSON (vd `ai.monthly_budget_vnd`, `store.name`). Khoá do module khai báo bằng `register_setting`. Riêng khoá `channel_account.<kênh>` là tài khoản kênh ở *Cài đặt → Mạng xã hội* (`app/integrations/channel_config.py`): `mode`, `values`, `secrets` (Fernet, không bao giờ trả ra API), `hints`, `meta` (tên tài khoản, hạn token), `check`, `oauth` (state đang chờ) — không hiện trong `GET /settings`. |
| `ai_provider_configs` | Cấu hình nhà cung cấp AI chị lưu ở Cài đặt (ghi đè env). Khoá chính `provider`; `is_active` (nhiều nhất một dòng, chỉ mục duy nhất có điều kiện); `api_key_encrypted` (Fernet, không bao giờ trả ra API), `api_key_hint` (dạng che), `key_updated_at`/`key_updated_by_id`; `base_url`, `model_smart`, `model_fast`, `effort_smart`, `effort_fast` (trống = lấy env); `updated_at`/`updated_by_id`. |
| `audit_log` | Lưu vết (k3): `actor_kind` (`owner`/`helper`/`ai`/`system`/`customer`), `actor_user_id`, `action` (vd `control.approved`, `auth.login`), `entity_type/entity_id`, `summary`, `data`. Chỉ ghi thêm. |

## sourcing — săn hàng (a1–a7)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `sourcing_briefs` | Đề tìm (a1). `raw_text` (lời chị), `input_mode`, `interpretation` (AI hiểu thế nào), `filters`, `keywords_vi`, `keywords_translated` `{zh,ja,en}`, `platforms`, `category_id`, khoảng giá, `is_scheduled` + `schedule_interval_days` + `next_run_at` + `alert_min_score` (a7), liên kết `demand_signal_id`/`find_request_id` khi đề sinh từ nhu cầu khách. Vòng đời: `draft` (chờ chị xác nhận cách hiểu) → `active` ⇄ `paused` → `done` / `archived`. |
| `sourcing_runs` | Một lượt AI đi tìm. `kind`: `brief_scan` (a4) · `link_import` (a2) · `image_search` (a3) · `scheduled_scan` (a7) · `trend_radar` (a5) · `demand_digest` (a6). `input`, `found_count`, `new_count`, `above_threshold_count`. Vòng đời: `queued` → `running` → `succeeded` / `failed` / `cancelled`. |
| `candidates` | Ứng viên: một sản phẩm cụ thể ở một nguồn. Nguồn (`source_platform`, `source_url`, `source_external_id` — duy nhất theo cặp), nội dung gốc + bản dịch (`title_original/title_vi`, `description_*`, `specs`, `variants`, `images`), giá nguồn (`price_amount`, `price_currency`, `price_vnd_estimate`), `moq`, `rating`, `review_count`, `sales_count`, xếp hạng (`ai_score` 0–100, `rank_reason` — c6), `image_hash`/`same_model_group` (gom cùng mẫu, a3/b7), `supplier_id`, `origin`. **`stage`** (bảng chọn c1): `candidate` → `sample` → `trial` → `selected` \| `rejected` (đổi ý được), `board_position` = thứ tự trong cột. |
| `trend_signals` | Radar xu hướng (a5): `platform`, `title`/`title_vi`, `url`, `reason` (vì sao đáng xem), `metrics`, `score`, `detected_on`. Vòng đời: `new` → `watching` → `converted` (có `candidate_id`) / `dismissed`. |
| `demand_signals` | Nhu cầu khách (a6) đã gộp: `title`, `normalized_key` (duy nhất), `ask_count` (số người khác nhau), `mention_count`, `last_asked_at`. Vòng đời: `open` → `searching` (đã mở đề, `find_request_id`/brief trỏ về) → `found` (`product_id`) / `dismissed`. |
| `demand_mentions` | Từng lần khách nhắc tới nhu cầu: `signal_id`, `source` (`comment`/`message`/`find_request`/`assistant`/`manual`), `customer_id`, `source_type/source_id` (vd `messages`), `text`. |

## assessment — thẩm định và so sánh (b1–b7)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `scoring_profiles` | Khung chấm của chị (b4): `criteria` `[{key,label,weight,description}]` (7 tiêu chí, tổng trọng số 100), `pass_score`, `category_id`, `is_default`. Seed tạo «Khung mặc định». |
| `assessments` | Hồ sơ thẩm định (b1), **một hồ sơ hiện hành cho mỗi ứng viên** (`candidate_id` duy nhất, `version` tăng khi chạy lại). `summary`, `strengths`, `weaknesses`, `specs`, `buyer_photos`, `price_overview`; chấm điểm `score_status` (`none` → `ai_draft` → `confirmed`), `score_total`; an toàn (b6) `safety_status` (`unchecked`/`ok`/`warning`/`blocked`) + `safety` (pin, chất lỏng, tiếp xúc thực phẩm, phải công bố...) + `safety_confirmed_*` (chị duyệt); hàng nhái/đánh giá ảo (b7) `counterfeit_risk`, `fake_review_risk`, `risk_notes`; `sources` (dẫn nguồn, dùng lại cho e7). Vòng đời: `pending` → `running` → `ready` / `failed`; `stale` khi nguồn đổi. |
| `assessment_scores` | Điểm từng tiêu chí: `criterion_key` (duy nhất trong hồ sơ), `weight`, `ai_score` + `ai_reason` (AI chấm nháp), `owner_score` + `owner_note` (chị sửa). |
| `review_digests` | Đọc hộ đánh giá (b2) theo từng lần đọc: `reviews_read`, `rating_avg`, `rating_histogram`, `praise`/`complaints` `[{point,count,quotes}]`, `low_star_summary`, `low_star_reviews`, `suspicious_ratio` + `suspicious_notes` (b7). |
| `market_prices` | Giá cùng món ở VN (b5): `candidate_id` hoặc `product_id`, `platform`, `shop_name`, `url`, `price_vnd`, `original_price_vnd`, `sold_count`, `match_confidence`, `captured_at`. Chỉ ghi thêm theo lần quét. |
| `comparisons` / `comparison_items` | Bảng so sánh (b3): tiêu chí `criteria`, `conclusion`, `recommended_candidate_id`; mỗi dòng `comparison_items` một ứng viên với `values` theo tiêu chí. |

## selection — bàn chọn (c1–c6)

Giai đoạn của bảng chọn là `candidates.stage` (module sourcing); module selection đổi `stage` qua hàm của sourcing hoặc
ghi trực tiếp — **thống nhất: chỉ module selection ghi `candidates.stage`/`stage_changed_at`/`board_position`**.

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `trial_notes` | Nhật ký thử hàng (c2): `kind` (`voice`/`text`/`photo`/`video`), `text` (chép lời), `audio_storage_key`, `media`, `recorded_at`, `trial_day`, `author` (`owner` / `tester` — h8 qua `tester_invite_id`), `ai_assigned` + `assignment_confidence` (AI xếp vào đúng món; `candidate_id` null khi chưa xếp được). `processing_status`: `pending` → `processing` → `done` / `failed`. |
| `selection_decisions` | Quyết định chọn/loại; nhiều dòng cho một ứng viên (đổi ý), dòng mới nhất (`decided_at`) là hiện hành. Chọn (c3): `draft_reason_selected`/`draft_not_satisfied` (AI soạn) → chị sửa → `reason_selected`/`not_satisfied`, `draft_status` `none` → `drafting` → `pending_review` → `approved`; `trial_days`, `product_id` khi đã thành sản phẩm. Loại (c4): `rejection_reason`, `rejection_tags`, `show_on_profile`. |
| `selection_principles` | Bộ nguyên tắc (c5): `kind` (`must`/`must_not`/`prefer`/`avoid`), `text`, `structured` (dạng máy đọc), `category_id` (null = mọi nhóm), `is_active`, `source` (`owner`/`ai_suggested`). |
| `taste_profiles` | Gu của chị (c6), một dòng cho mỗi nhóm hàng (+ một dòng chung `category_id` null): `summary`, `weights`, `examples`, `sample_count`, `version`, `trained_at`. |

## supply — nguồn cung và giá vốn (d1–d7)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `suppliers` | Sổ nhà cung cấp (d1): `kind` (`factory`/`shop`/`trading`/`purchasing_agent`/`forwarder`/`local_wholesaler`), `platform`, `shop_url`, `country`, `language`, `contact` (JSON), `trust_score`, `order_count`, `defect_rate`, `on_time_rate`, `avg_lead_days`, `agent_fee_pct`, `is_blocked`. |
| `cost_sheets` | Giá vốn về tay (d2) cho ứng viên hoặc sản phẩm: giá gốc (`unit_price_amount`, `currency`, `fx_rate`), các khoản VND (`unit_price_vnd`, `domestic_shipping_vnd`, `agent_fee_vnd`, `intl_shipping_vnd`, `tax_vnd`, `packaging_vnd`, `other_fees_vnd`, `loss_vnd`) → **`landed_cost_vnd` cho một cái**, `breakdown` để hiển thị, `is_current` (bản hiện hành), `auto_update` (tính lại khi tỷ giá/cước đổi), `version`. |
| `price_proposals` | Đề xuất giá bán (d3): `landed_cost_vnd`, giá thị trường thấp/giữa/cao, `target_margin_pct`, `proposed_price_vnd`, `margin_pct`, `rationale`, `approved_price_vnd`. Vòng đời: `draft` → `pending_review` → `approved` / `rejected`; `superseded` khi có đề xuất mới. |
| `purchase_orders` / `purchase_order_lines` | Đơn đặt mẫu/lô (d5, g3): `code`, `kind` (`sample`/`batch`/`restock`), `supplier_id`, `agent_supplier_id` (mua hộ), `drop_id` (đơn tổng hợp từ đợt), tiền (`subtotal_amount`, `fx_rate`, `total_vnd`, `deposit_vnd`, `paid_vnd`), `message_draft` (nội dung gửi NCC). Dòng: `description`, `quantity`, `unit_price_amount`, `unit_cost_vnd`, `received_qty`, `defect_qty`. Vòng đời: `draft` → `pending_approval` (**luôn chờ chị**) → `approved` → `sent` → `confirmed` → `paid` → `partially_received` → `received`; `cancelled`. |
| `supplier_messages` | Nhắn NCC (d6): `direction`, `channel`, `language`, `body_original`, `body_vi` (dịch), `extracted` (giá, MOQ, thời gian rút từ câu trả lời). Vòng đời đi: `draft` → `pending_review` → `approved` → `sent` / `failed`; đến: `received`. |
| `inbound_shipments` | Lô hàng về (d7): `status` `ordered` → `seller_shipped` → `at_agent_warehouse` → `international_transit` → `customs` → `domestic_transit` → `delivered`; `problem`. `milestones` (lịch sử mốc), `eta`, `weight_kg`, `shipping_cost_vnd`, `customs_cost_vnd`. |
| `provenance_documents` | Chứng từ nguồn gốc (d4): `kind` (hoá đơn, tờ khai, ảnh nhãn gốc, packing list, biên nhận, chứng nhận...), gắn với `purchase_order_id`/`inbound_shipment_id`/`product_id`/`supplier_id`, `storage_key` (`private/...`), `doc_number`, `doc_date`, `amount`, `extracted` (AI đọc). |

## catalog — website (e1–e3, e6, e8–e10)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `categories` | Nhóm hàng (cây qua `parent_id`): `slug` duy nhất, `is_consumable` + `default_reorder_days` (h6), `default_target_margin_pct`. |
| `products` | Sản phẩm trên web, **chỉ sinh từ ứng viên `selected`** (`candidate_id` duy nhất). Nội dung (e1): `name`, `subtitle`, `short_description`, `description` (markdown), `specs`, `faq`; hồ sơ chọn (e2): `selected_count`/`considered_count`, `trial_days`, `reason_selected`, `not_satisfied`, `rejected_alternatives`; giá `price_vnd`, `compare_at_price_vnd`, `landed_cost_vnd` (ảnh chụp); `sale_mode` (`drop`/`in_stock`/`both`); vận chuyển/an toàn `weight_grams`, `shipping_notes`; tiêu hao `is_consumable`, `reorder_days`; SEO/AI đọc (e10) `seo_*`, `gtin`, `brand`, `feed_enabled`; `rating_avg`, `review_count`. Vòng đời: `draft` → `pending_review` (AI dựng xong) → `published` ⇄ `paused` → `archived`. |
| `product_variants` | Phân loại (màu/cỡ): `name`, `sku` duy nhất, `options`, `price_vnd` (null = theo sản phẩm). |
| `product_images` | Ảnh (e6): `original_key` (ảnh thật chị chụp) + `processed_key` (đã cắt, cân sáng, làm sạch nền — không tạo ảnh giả), `processing_ops`, `kind`, `is_primary`, `position`, `ai_processed`. `status`: `raw` → `processing` → `processed` → `approved`; `failed`. |
| `drops` / `drop_items` | Đợt mở bán (e3): `code`, `slug`, `opens_at`, `closes_at` (hạn chót), `expected_arrival_date`, `deposit_pct`, `summary` (tổng hợp khi đóng — g3). Dòng: `product_id` (+ `variant_id`), `price_vnd`, `slots_total` (số suất), `slots_reserved`, `min_total_to_order`, `max_per_order`. Vòng đời: `draft` → `pending_review` → `scheduled` → `open` → `closed` → `sourcing` (đã đặt nguồn) → `arriving` → `fulfilling` → `completed`; `cancelled`. |
| `inventory_items` / `inventory_movements` | Tồn kho nhỏ (g8): một dòng cho mỗi (sản phẩm, phân loại): `on_hand`, `reserved` (`available` = hiệu), `low_stock_threshold`, `low_stock_alerted_at`, `unit_cost_vnd`. Mọi thay đổi ghi `inventory_movements` (`delta_on_hand`, `delta_reserved`, `reason`, `ref_type/ref_id`). |
| `reviews` | Đánh giá của khách (e8): `token` (link xin đánh giá), `order_item_id` (mỗi dòng hàng tối đa một đánh giá), `rating` 1–5, `body`, `photos`, `ai_flags`, `owner_reply`. Vòng đời: `requested` → `submitted` (AI lọc) → `pending_review` → `published` / `rejected`; `hidden`; `expired` (khách không gửi). |
| `find_requests` / `find_request_votes` | Nhờ tìm (e9): `public_slug`, `title`, `description`, `images`, `budget_vnd`, `contact`, `vote_count`, `vote_threshold`. Phiếu «cùng cần» duy nhất theo `voter_key` (băm). Vòng đời: `pending_review` → `open` → `threshold_reached` → `searching` (`brief_id`) → `found` (`product_id`) / `closed`; `rejected`. |

## orders — đơn hàng và vận hành (e4, e5, g1–g9)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `customers` | Khách, không cần tài khoản: `phone` (duy nhất, chuẩn hoá `0xxxxxxxxx`), `name`, `email`, `default_address`, `first_channel`, thống kê (`order_count`, `total_spent_vnd`, `first/last_order_at`), AI tóm tắt (`profile_summary`, `interests` — h4), `is_regular` (khách quen h5), `marketing_opt_in`, `merged_into_id` (gộp hồ sơ trùng), `referred_by_id`. |
| `customer_identities` | Định danh theo kênh (`channel`, `external_id` — duy nhất theo cặp): PSID Facebook, IG id, Zalo id... để hộp thư gộp nhận ra cùng một người. |
| `orders` | Đơn mọi kênh (g1): `code` (mã cho khách), `channel` + `external_id` (đơn sàn g9), `thread_id` (chốt từ tin nhắn g6), `drop_id`, người nhận + địa chỉ, tiền (`subtotal_vnd`, `shipping_fee_vnd`, `discount_vnd`, `total_vnd`, `paid_vnd`, `refunded_vnd`, `deposit_required_vnd`, `cod_amount_vnd`), `payment_method` (`bank_transfer`/`cod`/`marketplace`/`cash`), `payment_state` (`unpaid` → `partially_paid` → `paid`; `refunded`/`partially_refunded`), `transfer_content` (duy nhất, để khớp tiền g2), `referral_code`, các mốc thời gian. Tra cứu công khai (e5) bằng `recipient_phone` + `code`. **`status`**: `draft` (AI tạo từ tin nhắn, chờ chị) → `pending_payment` → `confirmed` → `awaiting_stock` (đơn trong đợt, hàng đang về) → `ready_to_ship` → `shipping` → `delivered` → `completed`; `cancelled`, `returned`. |
| `order_items` | Dòng hàng: `product_id`/`variant_id`/`drop_item_id`, `fulfillment_source` (`drop`/`stock`), ảnh chụp `name`/`sku`, `quantity`, `unit_price_vnd`, `line_total_vnd`, `unit_cost_vnd` (giá vốn lúc bán — dùng cho i5, k1). |
| `order_events` | Hành trình đơn (e5): `kind`, `status`, `title` (câu tiếng Việt cho khách), `visible_to_customer`, `actor`, `occurred_at`. Chỉ ghi thêm. |
| `payments` | Khoản tiền vào/ra: `direction` (`in`/`out` = hoàn tiền), `provider` + `external_id` (duy nhất), `amount_vnd`, `content` (nội dung CK), `received_at`, khớp đơn `order_id` + `match_method` (`auto_code`/`auto_amount`/`manual`/`cod_settlement`) + `match_confidence`, `refund_of_id`, `return_id`. Vòng đời: `received` → `matched` / `needs_review` (lệch tiền, nội dung lạ) / `ignored`; `refunded`; `failed`. |
| `shipments` / `shipment_events` | Vận đơn (g4): `carrier`, `service`, `tracking_code` (duy nhất theo hãng), `fee_vnd`, `cod_amount_vnd`, `quotes` (các báo giá đã so), `selection_reason`, `label_url`. Cũng dùng cho gửi mẫu (h8, `tester_invite_id`) và vận đơn hoàn (`return_id`). `status` theo `ShippingStatus`: `pending` → `created` → `picked_up` → `in_transit` → `out_for_delivery` → `delivered`; nhánh lỗi `failed_delivery` → `returning` → `returned`; `cancelled`. Sự kiện duy nhất theo (`status`, `occurred_at`). |
| `returns` | Đổi trả/hoàn tiền (g7, **luôn chờ chị**): `code`, `kind` (`return`/`exchange`/`refund_only`), `reason`, `photos`, `eligibility` (AI kiểm điều kiện), `proposal` (phương án AI soạn), `refund_amount_vnd`, `decision_note`. Vòng đời: `requested` → `pending_decision` → `approved` / `rejected` → `awaiting_item` → `received` → `refunded` / `exchanged` → `closed`. |
| `notifications` | Tin báo khách (g5) và tin tự động khác: `event` (mốc đơn, mời đánh giá, nhắc mua lại...), `channel`, `recipient`, `body`, `dedupe_key` (duy nhất — chống báo trùng một mốc). `status`: `queued` → `sent` / `failed` / `skipped`. |
| `marketplace_listings` | Đồng bộ sàn (g9): `marketplace` (`tiktok_shop`/`shopee`), `product_id`(+`variant_id`) duy nhất theo sàn, `external_id`, `price_vnd`, `synced_stock`, `last_synced_at`. `status`: `pending` → `active` ⇄ `inactive`; `error`. |

## assistant — trợ lý hỏi đáp trên web (e7)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `assistant_conversations` | Một phiên chat của khách ẩn danh (`session_key` từ cookie, `ip_hash`), `product_id` đang xem, `contact` khách để lại. Vòng đời: `open` → `handed_off` (chuyển chị: tạo `thread_id` trong hộp thư) → `closed`. |
| `assistant_messages` | `role` (`user`/`assistant`/`owner`), `content`, `citations` (`[{type,id,quote}]` trỏ tới hồ sơ thẩm định/sản phẩm/đánh giá), `basis`, `confidence`, `unknown` (không biết → chuyển chị), `feedback`. |

## content — xưởng nội dung (f1–f8)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `voice_profiles` | Giọng của chị (f2): `style_summary`, `rules`, `vocabulary`, `examples`, `sample_sources`, `channel_overrides`, `version`. Seed tạo «Giọng của chị». |
| `media_assets` | Tư liệu ảnh/clip/ghi âm: `kind`, `purpose` (`trial_clip`, `edited_video` f6, `voice_sample` f2...), `storage_key`, kích thước, `duration_seconds`, `parent_asset_id` (bản dựng từ clip gốc), `edit_spec` (cắt, phụ đề, gợi ý nhạc), `transcript`, `ai_generated`. `status`: `uploaded` → `processing` → `ready` → `pending_review` → `approved`; `failed`. |
| `content_drafts` | Bản nháp theo kênh (f1): `product_id`/`drop_id`, `channel`, `format` (`post`/`carousel`/`reel`/`video_script`/`zalo_message`/`story`), `title`, `body`, `hashtags`, `media_asset_ids`, `script`, `voice_profile_id`, `parent_draft_id` + `version` (soạn lại); soát lời (f5) `check_status` (`unchecked`/`passed`/`warnings`/`failed`) + `check_findings`; nhãn AI (k3) `ai_generated`, `ai_label_required`; `feedback_note`. Vòng đời: `drafting` → `pending_review` → `approved` / `returned` → `scheduled` → `published`; `archived`. |
| `scheduled_posts` | Lịch đăng (f3) + đăng tự động (f4): `draft_id`, `channel`, `channel_account_id`, `scheduled_at`, `external_post_id` (duy nhất theo kênh), `external_url`, `attempts`, `ai_label_applied`. Vòng đời: `planned` (AI xếp, chờ chị) → `approved` → `publishing` → `published` / `draft_pushed` (TikTok) / `failed`; `cancelled`. |
| `post_metrics` | Số liệu bài theo thời điểm (f7): reach, likes, comments, shares, saves, clicks, video_views, `messages_started`, `orders_attributed`, `revenue_attributed_vnd`. Chỉ ghi thêm. |
| `content_insights` | Rút kinh nghiệm theo kỳ (f7): `summary`, `findings` `[{pattern,evidence,recommendation}]`, `top_post_ids`. |
| `livestream_scripts` | Kịch bản livestream (f8): `outline`, `items` (thứ tự món + ý chính), `faq`. Vòng đời: `drafting` → `pending_review` → `approved` → `used`. |

## inbox — hộp thư gộp (h1–h3, g6)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `channel_accounts` | Trang/tài khoản của chị trên từng kênh (`channel`, `external_id` duy nhất theo cặp), `driver`, `can_publish`, `can_message`, `settings`. **Không lưu token** (token ở env/kho bí mật). `status`: `mock` / `connected` / `disconnected` / `error`. Seed tạo 4 tài khoản giả. |
| `threads` | Hội thoại: `kind` (`comment`/`direct_message`/`group`/`web_chat`), `external_thread_id` (duy nhất theo tài khoản), `external_post_id`/`scheduled_post_id` (bình luận dưới bài nào), `customer_id`, `last_intent`, `needs_owner` + `escalation_reason` (h3: khiếu nại, hàng lỗi, sức khoẻ, hoàn tiền...), `unread_count`, `product_id`, `order_id` (g6), `summary`. `status`: `open` → `waiting_customer` / `ai_handled` / `needs_owner` → `closed`; `spam`. |
| `messages` | Tin/bình luận: `direction`, `sender` (`customer`/`owner`/`helper`/`ai`), `external_message_id` (duy nhất trong thread), `body`, `attachments`, `sent_at`, `intent` + `intent_confidence`, `extracted` (món, số lượng, SĐT, địa chỉ — g6), `ai_generated`. `status`: đến `received`; đi `queued` → `sent` / `failed`. |
| `reply_drafts` | Câu trả lời AI soạn (h2): `kind` `instant` (giá/còn hàng/phí giao — tự gửi theo mức tự chủ) / `draft` (chờ chị), `intent`, `body`, `confidence`, `sources`, `draft_order` + `missing_info` (g6), `sent_message_id`. Vòng đời: `pending_review` → `approved` → `sent`; `auto_sent`; `rejected`; `superseded` (có tin mới). |

## crm — chăm khách (h4–h8)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `customer_notes` | Sổ khách (h4): `kind` (`note`/`interest`/`preference`/`issue`/`ai_summary`), `source` (`owner`/`ai`), `body`, `ref_type/ref_id` (rút từ đâu), `pinned`. |
| `customer_tags` | Nhãn khách (duy nhất theo khách + nhãn), `source`. Dùng cho chọn người nhận (h5, h6). |
| `broadcasts` | Tin gửi nhóm/nhiều khách (h5): `kind` (`drop_announcement`/`restock`/`general`), `channel`, `channel_account_id`, `drop_id`, `body`, `audience` (bộ lọc), `recipient_count`, `delivered_count`. Vòng đời: `draft` → `pending_review` → `approved` → `scheduled` → `sending` → `sent` / `failed`; `cancelled`. |
| `group_digests` | Tóm tắt thảo luận nhóm khách quen (h5): `thread_id`, kỳ, `summary`, `highlights`, `open_questions`, `product_mentions`. |
| `reorder_reminders` | Nhắc mua lại (h6), một nhắc cho mỗi dòng hàng tiêu hao (`order_item_id` duy nhất): `due_on`, `reason`, `channel`, `message_body`, `converted_order_id`. Vòng đời: `scheduled` → `pending_review` → `sent` → `converted`; `skipped` (khách không nhận tin / đã mua lại), `cancelled`. |
| `referrals` / `referral_uses` | Giới thiệu bạn (h7): mỗi khách một mã (`code` duy nhất), phần thưởng hai phía, `uses_count`, `rewarded_count`. Lượt dùng: mỗi khách được giới thiệu tối đa một lần; `pending` → `qualified` (đơn hoàn tất) → `rewarded`; `void`. |
| `tester_invites` | Khách thử hàng cùng chị (h8): `candidate_id` + `customer_id` (duy nhất theo cặp), `token` (link gửi cảm nhận), `feedback`, `feedback_rating`, `feedback_media`. Vòng đời: `draft` → `invited` → `accepted` / `declined` → `sample_sent` → `feedback_received` → `closed`. Cảm nhận cũng có thể ghi thành `trial_notes` (author `tester`). |

## finance — tài chính nền (i5, k1, k4, k5)

| Bảng | Mục đích · cột chính · vòng đời |
|---|---|
| `ledger_entries` | Sổ doanh thu, chi phí (k1): `entry_date` (giờ VN), `period` `YYYY-MM`, `kind` (`revenue`/`refund`/`cost_of_goods`/`shipping`/`payment_fee`/`marketplace_fee`/`expense`/`adjustment`), `direction`, `amount_vnd` (luôn dương), `document_no`, `source` (`auto`/`manual`), **`source_key` duy nhất** (chống ghi trùng, vd `order:<id>:revenue`), liên kết `order_id`/`payment_id`/`expense_id`/`invoice_id`/`purchase_order_id`. Doanh thu ghi khi đơn `confirmed` có tiền (CK) hoặc khi `delivered` (COD) — module finance chốt chi tiết. |
| `expenses` | Chi phí: `incurred_on`, `category` (`goods`/`samples`/`shipping`/`packaging`/`ads`/`ai`/`software`/`fees`/`tax`/`other`), `amount_vnd`, ngoại tệ gốc, `vendor`, `receipt_storage_key`, `is_deductible`. |
| `invoices` | Hoá đơn điện tử (k5): `reference` (duy nhất, chống phát hành trùng), `provider`, `series`, `number`, `lookup_code`, người mua, `lines`, `total_vnd`, `pdf/xml_storage_key`, `replaces_id`. Vòng đời: `draft` → `issuing` → `issued` / `failed`; `cancelled`, `replaced`. |
| `weekly_reports` | Báo cáo tuần (i5), một dòng mỗi tuần (`week_start` Thứ Hai, duy nhất): doanh thu, giá vốn, lãi gộp, chi phí, số đơn, khách quay lại, chi phí AI, `product_margins`, `top_posts`, `summary`, `highlights`. `status`: `generating` → `ready` / `failed`. |
| `backups` | Sao lưu (k4): `kind` (`database`/`storage`/`full`), `trigger` (`schedule`/`manual`), `storage_key` (`private/backups/...`), `size_bytes`, `checksum`. `status`: `running` → `succeeded` / `failed`. |
