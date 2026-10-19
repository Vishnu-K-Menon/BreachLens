-- Q3: How many people per address status?
SELECT address_status, COUNT(*) AS people
FROM people
GROUP BY address_status
ORDER BY people DESC;