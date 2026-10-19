-- Q2: How many people are READY / NEEDS_REVIEW / NOT_REQUIRED?
SELECT notify_status, COUNT(*) AS people
FROM notification_list
GROUP BY notify_status
ORDER BY people DESC;