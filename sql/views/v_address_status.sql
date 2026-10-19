-- People (golden records) and mentions per address status (ADR-050, ADR-063).
CREATE OR REPLACE VIEW v_address_status AS
WITH p AS (
    SELECT coalesce(people.address_status, 'NONE') AS status, count(*) AS people
    FROM people GROUP BY ALL
), m AS (
    SELECT coalesce(mentions.address_status, 'NONE') AS status, count(*) AS mentions
    FROM mentions GROUP BY ALL
)
SELECT status AS address_status, coalesce(p.people, 0) AS people, coalesce(m.mentions, 0) AS mentions
FROM p FULL OUTER JOIN m USING (status)
ORDER BY address_status;
