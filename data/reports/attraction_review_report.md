# Attraction review corpus

{
  "entity_type": "attraction",
  "canonical_entities": 3066,
  "matched_entities": 641,
  "entities_with_source_reviews": 641,
  "entities_with_text_reviews": 638,
  "text_coverage_percent": 20.808871493803,
  "raw_matched_reviews": 464954,
  "text_reviews": 231404,
  "ratings_only_reviews": 233550,
  "exact_duplicates_found": 6130,
  "duplicates_removed": 6130,
  "entities_requiring_cap": 254,
  "entities_at_100": 254,
  "entities_below_cap": 387,
  "processed_reviews": 36203,
  "date_min": "2008-02-04",
  "date_max": "2021-08-30"
}

## Source review-count distribution (includes zero-review matched entities)

```csv
measure,minimum,p25,median,p75,p90,p95,maximum,mean
total_reviews,1,28.0,136.0,633.0,2018.0,3356.0,9998,725.3572542901716
text_reviews,0,12.0,57.0,253.0,975.0,1532.0,9998,361.0046801872075
unique_text_reviews,0,12.0,57.0,252.0,942.0,1525.0,9998,351.5117004680187
```

## Text-review count bins

```csv
text_reviews,count
0,3
1–4,54
5–9,82
10–24,89
25–49,76
50–99,81
100+,256

```

## Processed rating distribution

```csv
rating,count
1.0,2532
2.0,2023
3.0,4309
4.0,7946
5.0,19393

```

## Processed date distribution (UTC year)

```csv
review_date,count
2008,2
2009,1
2010,5
2011,19
2012,45
2013,149
2014,158
2015,389
2016,1395
2017,3240
2018,5463
2019,10966
2020,9220
2021,5151

```

## Unique source rating distribution (before cap; text and ratings-only)

```csv
rating,unique_reviews
1.0,11234
2.0,8790
3.0,35244
4.0,99774
5.0,303782
```

## Unique source date distribution (before cap; UTC year)

```csv
utc_year,unique_reviews
2005,3
2008,4
2009,7
2010,140
2011,370
2012,513
2013,1424
2014,1777
2015,4671
2016,20420
2017,57700
2018,123897
2019,175037
2020,57817
2021,15044
```

## Category coverage

```csv
category,canonical,matched,with_text,processed_reviews
amusement,7,2,2,148.0
beach,49,5,5,182.0
garden,365,42,41,692.0
historic_site,41,5,5,194.0
landmark,190,38,38,1837.0
market,1,0,0,0.0
museum,100,42,42,3724.0
park,1302,339,339,18438.0
religious_site,24,11,11,398.0
sports,655,63,61,2019.0
theater,214,85,85,8003.0
transport_landmark,9,4,4,129.0
zoo,109,5,5,439.0

```
