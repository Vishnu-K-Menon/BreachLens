-- Q4: List minors who need a guardian notice (person id, state, note).
SELECT p.person_id, n.jurisdiction, n.notify_status, n.notify_note
FROM people p
JOIN notification_list n
  ON p.run_id = n.run_id
 AND p.person_id = n.person_id
WHERE p.is_minor
  AND n.notify_required
ORDER BY p.person_id;