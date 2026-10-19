-- Open review items (ADR-062): one row per column-level warning (with affected_rows),
-- one per mention with its own row-level codes, one per gray-zone pair.
CREATE OR REPLACE VIEW v_review_queue AS
SELECT item_type, item_id, doc_id, sheet, header, mention_id, person_id, codes, severity, affected_rows
FROM review_items
WHERE status = 'OPEN'
ORDER BY CASE severity WHEN 'ERROR' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END,
         affected_rows DESC, item_id;
