# NYC LPC landmark audit

Audit only; no taxonomy changes during matching, final attraction IDs, processed attractions table or source union.
## Source schema, missingness, duplicates and status accounting

```json
{
  "individual": {
    "source_coordinate_validation": {
      "rows_checked": 1465,
      "outside_polygon_by_over_0_002_degrees": 56,
      "maximum_offset_degrees": 0.019677835813819537
    },
    "metadata": {
      "dataset_name": "Individual Landmark Sites",
      "dataset_id": "buis-pvji",
      "retrieved_at": "2026-10-10T10:02:44.210867+00:00",
      "row_count": 1532,
      "source_url": "https://data.cityofnewyork.us/d/buis-pvji",
      "download_url": "https://data.cityofnewyork.us/api/geospatial/buis-pvji?method=export&format=GeoJSON",
      "schema_url": "https://data.cityofnewyork.us/api/views/buis-pvji.json",
      "geometry_crs": "GEOGCS[\"WGS 84\", DATUM[\"WGS84\", SPHEROID[\"WGS84\", 6378137.0, 298.257223563]], PRIMEM[\"Greenwich\", 0.0], UNIT[\"degree\", 0.017453292519943295], AXIS[\"Geodetic longitude\", EAST], AXIS[\"Geodetic latitude\", NORTH], AUTHORITY[\"EPSG\",\"4326\"]]",
      "geometry_note": "Socrata geometry is native EPSG:2263; exported .prj incorrectly labels projected coordinates WGS84. LPC service metadata resolves the conflict.",
      "projection_download_url": "https://data.cityofnewyork.us/api/geospatial/buis-pvji?method=export&format=Shapefile",
      "checksums": {
        "landmarks.zip": "2dcab1073789c16fac193f0ce5f2fc83472ecd6acac9be0923630be58788f52d",
        "source_projection.prj": "e36f7d4ec22975852e267a37d40ef1da7cfb4fa84ef6c28ae9794432f125644c",
        "landmarks.geojson": "abf074a25f73208acbffeffa5c7f7f140e2e57352e17f4d10bcd2abb74da0af9",
        "source_schema.json": "a68bec24461508338b40735adce2334f94a517cf3c5219f77e766e7e0b92f883",
        "lpc_crs_metadata.json": "664dde0785d20caa769d6545f11ad6a29f2bcd462980f35144756064849abaa8"
      },
      "geometry_epsg": 2263,
      "crs_evidence_url": "https://services5.arcgis.com/Oos4pNA2538iVFA1/ArcGIS/rest/services/Ind_Landmark_Lots_POLY/FeatureServer?f=pjson"
    },
    "api_columns": [
      "bct2020",
      "shape_area",
      "latitude",
      "lpc_sitest",
      "cd",
      "bbl",
      "council",
      "objectid",
      "lpc_sitede",
      "longitude",
      "shape_leng",
      "desdate",
      "block",
      "lpc_altern",
      "url_report",
      "lot",
      "address",
      "nta2020",
      "landmarkty",
      "lpc_lpnumb",
      "borough",
      "lpc_name"
    ],
    "export_columns": [
      "objectid",
      "borough",
      "block",
      "lot",
      "address",
      "bbl",
      "lpc_name",
      "lpc_lpnumb",
      "lpc_sitede",
      "lpc_sitest",
      "lpc_altern",
      "desdate",
      "landmarkty",
      "url_report",
      "cd",
      "council",
      "latitude",
      "longitude",
      "bct2020",
      "nta2020",
      "shape_leng",
      "shape_area"
    ],
    "api_dtypes": {
      "bct2020": "str",
      "shape_area": "str",
      "latitude": "str",
      "lpc_sitest": "str",
      "cd": "str",
      "bbl": "str",
      "council": "str",
      "objectid": "str",
      "lpc_sitede": "str",
      "longitude": "str",
      "shape_leng": "str",
      "desdate": "str",
      "block": "str",
      "lpc_altern": "str",
      "url_report": "object",
      "lot": "str",
      "address": "str",
      "nta2020": "str",
      "landmarkty": "str",
      "lpc_lpnumb": "str",
      "borough": "str",
      "lpc_name": "str"
    },
    "api_missingness": {
      "bct2020": 67,
      "shape_area": 0,
      "latitude": 67,
      "lpc_sitest": 0,
      "cd": 67,
      "bbl": 0,
      "council": 67,
      "objectid": 0,
      "lpc_sitede": 1,
      "longitude": 67,
      "shape_leng": 0,
      "desdate": 0,
      "block": 0,
      "lpc_altern": 1107,
      "url_report": 1532,
      "lot": 0,
      "address": 1,
      "nta2020": 3,
      "landmarkty": 0,
      "lpc_lpnumb": 0,
      "borough": 5,
      "lpc_name": 0
    },
    "exact_duplicate_attribute_rows": 0,
    "unique_landmark_names": 1504,
    "status_counts": {
      "designated; current flag unavailable": 1514,
      "other current states": 18
    },
    "status_values": {
      "Designated": 1514,
      "Amended": 8,
      "Proposed": 6,
      "Moved": 3,
      "Heard": 1
    },
    "current_values": {
      "None": 1532
    }
  },
  "scenic": {
    "source_coordinate_validation": "Scenic extents verified against LPC EPSG:2263 geometry during download",
    "metadata": {
      "dataset_name": "Scenic Landmarks",
      "dataset_id": "qexa-qpj6",
      "retrieved_at": "2026-10-10T10:02:51.538061+00:00",
      "row_count": 8,
      "source_url": "https://data.cityofnewyork.us/d/qexa-qpj6",
      "download_url": "https://data.cityofnewyork.us/api/geospatial/qexa-qpj6?method=export&format=GeoJSON",
      "schema_url": "https://data.cityofnewyork.us/api/views/qexa-qpj6.json",
      "geometry_crs": "GEOGCS[\"WGS 84\", DATUM[\"WGS84\", SPHEROID[\"WGS84\", 6378137.0, 298.257223563]], PRIMEM[\"Greenwich\", 0.0], UNIT[\"degree\", 0.017453292519943295], AXIS[\"Geodetic longitude\", EAST], AXIS[\"Geodetic latitude\", NORTH], AUTHORITY[\"EPSG\",\"4326\"]]",
      "geometry_note": "Socrata geometry is native EPSG:2263; exported .prj incorrectly labels projected coordinates WGS84. LPC service metadata resolves the conflict.",
      "projection_download_url": "https://data.cityofnewyork.us/api/geospatial/qexa-qpj6?method=export&format=Shapefile",
      "checksums": {
        "landmarks.zip": "2b7eae0ab777226b14cf861e617e6a721cb03b380a52846917d09649d52e76da",
        "source_projection.prj": "e36f7d4ec22975852e267a37d40ef1da7cfb4fa84ef6c28ae9794432f125644c",
        "landmarks.geojson": "f059f08667bc3e9d5bef97e8fd12d24534f3911ddf4426a07ceaf3fe8d5deca9",
        "source_schema.json": "442a03349d97dff195f464e9b76d7fe4816ca277d8a9a7aa4bf9934833c4c34f",
        "lpc_crs_metadata.json": "9054ed5df8e550c77e0d50bc8ae80da5c1f7fe6c8eec54e456e831c4b3f2b9fd"
      },
      "geometry_epsg": 2263,
      "crs_evidence_url": "https://services5.arcgis.com/Oos4pNA2538iVFA1/ArcGIS/rest/services/Scenic/FeatureServer/0/query?where=1%3D1&outFields=LP_NUMBER&returnGeometry=true&outSR=2263&f=json"
    },
    "api_columns": [
      "last_actio",
      "shape_area",
      "caldate",
      "current_",
      "public_hea",
      "shape_leng",
      "desdate",
      "status",
      "lp_number",
      "scen_lm_na",
      "borough"
    ],
    "export_columns": [
      "borough",
      "lp_number",
      "current_",
      "scen_lm_na",
      "status",
      "last_actio",
      "public_hea",
      "date_desda",
      "time_desda",
      "date_calda",
      "time_calda",
      "shape_leng",
      "shape_area"
    ],
    "api_dtypes": {
      "last_actio": "str",
      "shape_area": "str",
      "caldate": "str",
      "current_": "str",
      "public_hea": "str",
      "shape_leng": "str",
      "desdate": "str",
      "status": "str",
      "lp_number": "str",
      "scen_lm_na": "str",
      "borough": "str"
    },
    "api_missingness": {
      "last_actio": 0,
      "shape_area": 0,
      "caldate": 6,
      "current_": 0,
      "public_hea": 0,
      "shape_leng": 0,
      "desdate": 0,
      "status": 0,
      "lp_number": 0,
      "scen_lm_na": 0,
      "borough": 0
    },
    "exact_duplicate_attribute_rows": 0,
    "unique_landmark_names": 8,
    "status_counts": {
      "current + designated": 8
    },
    "status_values": {
      "DESIGNATED": 8
    },
    "current_values": {
      "true": 8
    }
  }
}
```

Individual Sites has lpc_sitest but no MOST_CURRENT/current flag or LAST_ACTION field. Only designated rows are eligible; currency cannot be independently verified and is not imputed.
Scenic Landmarks requires current_=true and status=DESIGNATED; contradictory rescinded/inactive/calendared actions block eligibility.
All raw records and status groups remain in the clean tables; only eligible rows enter matching. Unknown/non-designated states are not accepted.

## Geometry and matching

Socrata GeoJSON contains native projected coordinates despite its format name. Geometry is transformed from EPSG:2263 using LPC service metadata: the Socrata Shapefile .prj incorrectly labels its projected coordinates WGS84. This metadata conflict is preserved in retrieval metadata; transformed individual points are validated against source latitude/longitude. Source identities and row counts are checked between exports.
Representative points are guaranteed covered by the polygon; invalid polygons are deterministically repaired and flagged. No external geocoding.
Names reuse Unicode/punctuation normalization. Fuzzy threshold=0.94. Names need <=50m corroboration; exact names allow <=150m. Exact or high-confidence fuzzy names also accept polygon containment, even for large polygons whose representative point is farther away.
Distance is Haversine distance to the representative point; containment is reported separately. Nearby different names and name-only matches are not accepted. Multiple supported records remain AMBIGUOUS. Source features retain distinct references; these are not canonical attraction IDs.
## Match-status accounting (one row per eligible source feature)

| landmark_source | MATCHED_INCLUDE | MATCHED_REVIEW | MATCHED_EXCLUDE | UNMATCHED | AMBIGUOUS | REJECTED |
| --- | --- | --- | --- | --- | --- | --- |
| nyc_lpc_individual_landmarks | 33 | 32 | 20 | 1415 | 0 | 14 |
| nyc_lpc_scenic_landmarks | 3 | 1 | 0 | 4 | 0 | 0 |

Full matching report contains candidate pairs; use matching_summary for source-row counts. Unique CommonPlace support is counted separately by subtype. Repeated LP numbers/features are preserved rather than silently deduplicated.
## Supported REVIEW examples

| landmark_source | landmark_source_id | landmark_name | borough | designation_address | lp_number | commonplace_source_id | commonplace_name | commonplace_filter_decision | facility_type | facility_domain_code | facility_domain_label | distance_meters | geometry_contains | match_method | match_confidence | match_status | evidence_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nyc_lpc_individual_landmarks | 1322 | McCarren Play Center | BK | Lorimer Street, between Driggs Avenue and Bayard Street | LP-02244 | 8578 | MCCARREN PLAY CENTER | REVIEW | 4 | 7 | Recreational Center | 35.21972260201341 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1303 | Brinckerhoff Cemetery | QN | 69-65 to 69-73 182nd Street | LP-02087 | 20037 | BRINCKERHOFF CEMETERY | REVIEW | 13 | 3 | Cemetery/Morgue | 6.793184819243812 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1276 | Antioch Baptist Church | BK | 828 and 826 Greene Avenue | LP-01790 | 9258 | ANTIOCH BAPTIST CHURCH | REVIEW | 9 | 1 | Church | 5.061703306550036 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1243 | Saint Alban's Episcopal Church | SI | 76 Saint Alban's Place | LP-01113 | 4695 | ST ALBANS EPISCOPAL CHURCH | REVIEW | 9 | 1 | Church | 10.438282086598395 | True | fuzzy_name_polygon_contains | 0.945455 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1186 | Squadron A Armory | MN | Madison Avenue between East 94th and 95th Streets | LP-00398 | 1015 | SQUADRON A ARMORY | REVIEW | 3 | 5 | Other | 84.27476584439647 | False | exact_name_within_150m | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1156 | New Lots Reformed Church | BK | 630 New Lots Avenue | LP-00169 | 11405 | NEW LOTS REFORMED CHURCH | REVIEW | 9 | 1 | Church | 4.698861933581984 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1137 | Chapel of the Good Shepherd | MN | Roosevelt Island, located approximately opposite East 68th Street | LP-00907 | 17347 | CHAPEL OF THE GOOD SHEPHERD | REVIEW | 9 | 1 | Church | 12.903212159236132 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1130 | Whitehall Ferry Terminal | MN | 11 South Street | LP-00547 | 11608 | WHITEHALL FERRY TERMINAL | REVIEW | 6 | 2 | Ferry landing/terminal | 127.99471041889609 | False | exact_name_within_150m | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1128 | Pier A | MN | Battery Park | LP-00918 | 8477 | PIER A | REVIEW | 6 | 7 | Pier | 38.36685713551816 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1064 | Saint Mary's Episcopal Church | BK | 230 Classon Avenue | LP-02013 | 4609 | ST MARYS EPISCOPAL CHURCH | REVIEW | 9 | 1 | Church | 4.939876843901007 | True | fuzzy_name_polygon_contains | 0.943396 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1044 | Grace Memorial House | MN | 94-96 Fourth Avenue | LP-00853 | 21412 | GRACE MEMORIAL HOUSE | REVIEW | 9 | 6 | Other | 1.0973954343542907 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1043 | Grace Church | MN | 800 Broadway | LP-00203 | 1751 | GRACE CHURCH | REVIEW | 9 | 1 | Church | 13.154026245121738 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 982 | Williamsbridge Reservoir Keeper's House | BX | 3400 Resevoir Oval | LP-02047 | 18637 | WILLIAMSBRIDGE RESERVOIR KEEPERS HOUSE | REVIEW | 4 | 10 | Other | 6.936633201803681 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 976 | Riverdale Presbyterian Church | BX | 4765 Henry Hudson Parkway | LP-00128 | 8590 | RIVERDALE PRESBYTERIAN CHURCH | REVIEW | 9 | 1 | Church | 44.48351688642545 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 970 | Bedford Park Congregational Church | BX | 2988 Bainbridge Avenue | LP-02062 | 8285 | BEDFORD PARK CONGREGATION CHURCH | REVIEW | 9 | 1 | Church | 20.087666353956024 | False | fuzzy_name_within_50m | 0.969697 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 941 | Tremont Baptist Church | BX | 324 East Tremont Avenue | LP-02048 | 5731 | TREMONT BAPTIST CHURCH | REVIEW | 9 | 1 | Church | 2.509713183540122 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 916 | Hendrick I. Lott House | BK | 1940 East 36th Street | LP-01705 | 13509 | HENDRICK I LOTT HOUSE | REVIEW | 13 | 4 | Other | 18.51982272841024 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 867 | Emmanuel Baptist Church | BK | 279 Lafayette Avenue | LP-00160 | 11493 | EMMANUEL BAPTIST CHURCH | REVIEW | 9 | 1 | Church | 6.927975610493396 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 830 | Weir Greenhouse | BK | 5th Avenue at 25th Street | LP-01197 | 10502 | WEIR GREENHOUSE | REVIEW | 3 | 5 | Other | 5.2670295187744385 | True | exact_name_polygon_contains | 1.0 | MATCHED_REVIEW | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 746 | Saint Martin's Episcopal Church | MN | 230 Lenox Avenue | LP-00293 | 6612 | ST MARTINS EPISCOPAL CHURCH | REVIEW | 9 | 1 | Church | 11.543556289956921 | True | fuzzy_name_polygon_contains | 0.947368 | MATCHED_REVIEW | Name and geometry/location corroborate identity |

## Supported EXCLUDE examples

| landmark_source | landmark_source_id | landmark_name | borough | designation_address | lp_number | commonplace_source_id | commonplace_name | commonplace_filter_decision | facility_type | facility_domain_code | facility_domain_label | distance_meters | geometry_contains | match_method | match_confidence | match_status | evidence_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nyc_lpc_individual_landmarks | 1292 | Pratt Institute Library | BK | 224-228 Ryerson Street | LP-02011 | 14597 | PRATT INSTITUTE LIBRARY | EXCLUDE | 2 | 7 | Post Secondary Degree Granting Institution | 5.356291129661693 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1289 | CBS Building | MN | 51 West 52nd Street | LP-01971 | 1692 | CBS BUILDING | EXCLUDE | 7 | 2 | Business | 8.415948249209215 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1251 | South Congregational Church Complex | BK | 358-366 Court Street and 253-269 President Street | LP-01245 | 5191 | SOUTH CONGREGATIONAL CHURCH COMPLEX | EXCLUDE | 1 | 2 | Private Development | 15.229879058812712 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1248 | Curtis High School | SI | 105 Hamilton Avenue at St. Mark's Place | LP-01214 | 9662 | CURTIS HIGH SCHOOL | EXCLUDE | 2 | 3 | Public High School | 30.802658048520843 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1176 | Edgewater Village Hall | SI | 111 Canal Street in Tappan Park | LP-00350 | 17657 | EDGEWATER VILLAGE HALL | EXCLUDE | 8 | 1 | Government Office | 3.088902832283506 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 1067 | Gracie Mansion | MN | East End Avenue at East 88th Street | LP-00179 | 15147 | GRACIE MANSION | EXCLUDE | 8 | 7 | Other | 19.786107668975536 | False | exact_name_within_50m | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 891 | Renaissance Apartments | BK | 488 Nostrand Avenue and 140-144 Hancock Street | LP-01433 | 6212 | RENAISSANCE APARTMENTS | EXCLUDE | 1 | 2 | Private Development | 3.817249979865334 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 888 | Imperial Apartments | BK | 1198 Pacific Street and 1327-1339 Bedford Avenue | LP-01432 | 3106 | IMPERIAL APARTMENTS | EXCLUDE | 1 | 2 | Private Development | 12.225947060499312 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 882 | Alhambra Apartments | BK | 500-518 Nostrand Avenue | LP-01431 | 6253 | ALHAMBRA APARTMENTS | EXCLUDE | 1 | 2 | Private Development | 9.441088970740772 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 716 | Seagram Building | MN | 375 Park Avenue | LP-01664 | 2330 | SEAGRAM BUILDING | EXCLUDE | 7 | 2 | Business | 6.589108911200999 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 616 | Waldorf-Astoria Hotel | MN | 301 Park Avenue | LP-01812 | 4752 | WALDORF ASTORIA HOTEL | EXCLUDE | 7 | 4 | Hotel/Motel | 45.8685410100835 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 601 | Belleclaire Hotel | MN | 2171-2179 Broadway | LP-01507 | 8662 | BELLECLAIRE HOTEL | EXCLUDE | 7 | 4 | Hotel/Motel | 13.741056012608619 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 561 | 369th Regiment Armory | MN | 2360 Fifth Avenue | LP-01390 | 8014 | 369 REGIMENT ARMORY | EXCLUDE | 8 | 6 | Military | 55.12806182766847 | True | fuzzy_name_polygon_contains | 0.95 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 556 | Daily News Building | MN | 220 East 42nd Street | LP-01049 | 1704 | DAILY NEWS BUILDING | EXCLUDE | 7 | 2 | Business | 32.26041778595792 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 398 | Paramount Hotel | MN | 235-245 West 46th Street | LP-02342 | 12561 | PARAMOUNT HOTEL | EXCLUDE | 7 | 4 | Hotel/Motel | 9.751430694814248 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 299 | City Hall | MN | City Hall Park | LP-00080 | 7116 | CITY HALL | EXCLUDE | 8 | 1 | Government Office | 21.9582226054949 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 269 | Algonquin Hotel | MN | 59-61 West 44th Street | LP-01547 | 4070 | ALGONQUIN HOTEL | EXCLUDE | 7 | 4 | Hotel/Motel | 10.142057028353719 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 89 | Flushing High School | QN | 35-01 Union Street | LP-01798 | 21143 | FLUSHING HIGH SCHOOL | EXCLUDE | 2 | 3 | Public High School | 74.4069549168615 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 76 | Newtown High School | QN | 48-01 90th Street | LP-02131 | 21008 | NEWTOWN HIGH SCHOOL | EXCLUDE | 2 | 3 | Public High School | 22.968669930801962 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |
| nyc_lpc_individual_landmarks | 8 | Staten Island Borough Hall | SI | 2-10 Richmond Terrace | LP-01207 | 8047 | STATEN ISLAND BOROUGH HALL | EXCLUDE | 8 | 1 | Government Office | 9.293755356699739 | True | exact_name_polygon_contains | 1.0 | MATCHED_EXCLUDE | Name and geometry/location corroborate identity |

## Unmatched scenic landmarks

| landmark_name | borough | match_status | inspection_keywords |
| --- | --- | --- | --- |
| Grand Army Plaza | MN | UNMATCHED |  |
| Prospect Park | BK | UNMATCHED | park |
| Fort Tryon Park | MN | UNMATCHED | park |
| Coney Island (Riegelmann) Boardwalk | BK | UNMATCHED |  |

## Unmatched individual examples

| landmark_name | designation_address | borough | match_status | inspection_keywords |
| --- | --- | --- | --- | --- |
| Church of Saint Mary | 440 GRAND STREET | MN | UNMATCHED | church |
| Public School 15 Annex | 362 SCHERMERHORN STREET | BK | UNMATCHED |  |
| Lithuanian Alliance Building | 307 WEST 30 STREET | MN | UNMATCHED |  |
| Lefcourt Clothing Center | 275 7 AVENUE | MN | UNMATCHED |  |
| Barbey Building | 15 WEST 38 STREET | MN | UNMATCHED |  |
| Furcraft Building | 242 WEST 30 STREET | MN | UNMATCHED |  |
| 29th Street Towers | 224 WEST 29 STREET | MN | UNMATCHED |  |
| Fashion Tower | 135 WEST 36 STREET | MN | UNMATCHED |  |
| 29th Street Towers | 214 WEST 29 STREET | MN | UNMATCHED |  |
| (Former) Whitney Museum of American Art | 945 Madison Avenue | MN | UNMATCHED | museum |
| Jacob Day Residence | 50 West 13 Street | MN | UNMATCHED |  |
| Brooklyn Edison Building | 345 Adams Street (aka 372-392 Pearl Street, 11-17 Willoughby Street) | BK | UNMATCHED |  |
| Heckscher Building (now the Crown Building) | 730 Fifth Avenue (aka 728-734 Fifth Avenue, 2-4 West 57th Street) | MN | UNMATCHED |  |
| New York Public Library, Tremont Branch | 1866 Washington Avenue | BX | UNMATCHED | library |
| Modulightor Building | 246 East 58th Street | MN | UNMATCHED |  |
| Barkin, Levin & Company Office Pavilion | 12-12 33rd Avenue | QN | UNMATCHED |  |
| Joseph Rodman Drake Park and Enslaved People's Burial Ground | Oak Point Avenue, Drake Park South, Longfellow Avenue, and Hunts Point Avenue | BX | UNMATCHED | park |
| Hotel Cecil & Minton's Playhouse Building | 206 West 118th Street (aka 150-158 St. Nicholas Avenue, 206-212 West 118th Street) | MN | UNMATCHED |  |
| 935 St. Nicholas Avenue Building | 935 St. Nicholas Avenue (aka 929-939 St. Nicholas Avenue, 426-466 West 157th Street) | MN | UNMATCHED |  |
| John Birks "Dizzy" Gillespie Residence | 105-19 37th Avenue (aka 34-68 106th Street) | QN | UNMATCHED |  |
| Firehouse, Engine Company 88 / Ladder Company 38 | 2225 Belmont Avenue | BX | UNMATCHED |  |
| Bronx Opera House | 436-442 East 149th Street | BX | UNMATCHED | house |
| Fire Alarm Telegraph Bureau, Bronx Central Office | 1129 East 180th Street | BX | UNMATCHED |  |
| (Former) Colored School No. 4 | 128 West 17th Street | MN | UNMATCHED |  |
| Julius' Bar Building | 155-159 West 10th Street (aka 186-188 Waverly Place) | MN | UNMATCHED |  |
| Samuel Gompers Industrial High School | 455 Southern Boulevard (aka 462 Wales Avenue) | BX | UNMATCHED |  |
| The Lesbian Herstory Archives | 484 14th Street | BK | UNMATCHED |  |
| Kimlau War Memorial | Chatham Square and East Broadway | MN | UNMATCHED | memorial |
| Aakawaxung Munahanung (Island Protected from the Wind) Archaeological Site | Conference House Park, 258 Satterlee Street (aka 298-300 Satterlee Street) | SI | UNMATCHED |  |
| New York Public Library, Harlem Branch | 9 West 124th Street | MN | UNMATCHED | library |

Keyword flags are inspection aids; individual designation does not establish tourist suitability or public access.
## Borough distribution (all clean rows)

| source | borough | rows |
| --- | --- | --- |
| nyc_lpc_individual_landmarks |  | 5 |
| nyc_lpc_individual_landmarks | BK | 212 |
| nyc_lpc_individual_landmarks | BX | 101 |
| nyc_lpc_individual_landmarks | MN | 989 |
| nyc_lpc_individual_landmarks | QN | 86 |
| nyc_lpc_individual_landmarks | SI | 139 |
| nyc_lpc_scenic_landmarks | BK | 2 |
| nyc_lpc_scenic_landmarks | MN | 6 |
