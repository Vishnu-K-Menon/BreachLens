-- Q1: How many people get a notice in each state?
SELECT jurisdiction, COUNT(*) AS people_notified
FROM notification_list
WHERE notify_required
GROUP BY jurisdiction
ORDER BY jurisdiction;