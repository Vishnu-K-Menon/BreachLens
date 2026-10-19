-- Q5: Top 10 validation reason codes by count.
WITH codes AS (
    SELECT unnest(string_split(qc_reasons, ';')) AS code
    FROM mentions
    WHERE qc_reasons IS NOT NULL
      AND qc_reasons <> ''
)
SELECT code, COUNT(*) AS n
FROM codes
GROUP BY code
ORDER BY n DESC, code
LIMIT 10;