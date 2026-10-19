-- People and notices per jurisdiction (golden-record state), for the latest loaded run.
CREATE OR REPLACE VIEW v_notify_by_state AS
SELECT
    n.jurisdiction,
    count(*)                                              AS people,
    count(*) FILTER (WHERE n.notify_required)             AS to_notify,
    count(*) FILTER (WHERE n.notify_status = 'NEEDS_REVIEW') AS needs_review,
    count(*) FILTER (WHERE p.is_minor)                    AS minors,
    count(*) FILTER (WHERE n.ferpa_flag)                  AS ferpa_flagged
FROM notification_list AS n
JOIN people AS p USING (run_id, person_id)
GROUP BY n.jurisdiction
ORDER BY n.jurisdiction;
