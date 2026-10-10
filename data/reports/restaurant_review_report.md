# Restaurant review corpus

{
  "entity_type": "restaurant",
  "canonical_entities": 670,
  "matched_entities": 246,
  "entities_with_source_reviews": 246,
  "entities_with_text_reviews": 246,
  "text_coverage_percent": 36.71641791044776,
  "raw_matched_reviews": 131200,
  "text_reviews": 73766,
  "ratings_only_reviews": 57434,
  "exact_duplicates_found": 1618,
  "duplicates_removed": 1618,
  "entities_requiring_cap": 158,
  "entities_at_100": 158,
  "entities_below_cap": 88,
  "processed_reviews": 20349,
  "date_min": "1990-12-31",
  "date_max": "2021-08-20"
}

## Source review-count distribution (includes zero-review matched entities)

```csv
measure,minimum,p25,median,p75,p90,p95,maximum,mean
total_reviews,7,115.0,277.0,576.25,1174.5,1956.0,8437,533.3333333333334
text_reviews,5,67.0,149.5,334.25,715.5,1045.25,4701,299.8617886178862
unique_text_reviews,5,65.5,149.0,334.0,671.5,1030.75,4701,293.3211382113821
```

## Text-review count bins

```csv
text_reviews,count
0,0
1–4,0
5–9,4
10–24,13
25–49,20
50–99,51
100+,158

```

## Processed rating distribution

```csv
rating,count
1.0,2516
2.0,1409
3.0,2043
4.0,3585
5.0,10796

```

## Processed date distribution (UTC year)

```csv
review_date,count
1990,1
2005,1
2006,2
2007,1
2008,3
2009,5
2010,13
2011,27
2012,53
2013,114
2014,118
2015,300
2016,711
2017,1587
2018,2966
2019,5005
2020,5838
2021,3604

```

## Unique source rating distribution (before cap; text and ratings-only)

```csv
rating,unique_reviews
1.0,6674
2.0,4016
3.0,10922
4.0,29246
5.0,78724
```

## Unique source date distribution (before cap; UTC year)

```csv
utc_year,unique_reviews
1990,14
2002,4
2003,8
2004,3
2005,15
2006,19
2007,20
2008,48
2009,34
2010,165
2011,369
2012,511
2013,908
2014,909
2015,1871
2016,6667
2017,16701
2018,35265
2019,41848
2020,17958
2021,6245
```
