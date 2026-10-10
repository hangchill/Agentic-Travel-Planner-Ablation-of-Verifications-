# First CommonPlace attraction candidate universe

Candidate policy only: no final attraction IDs, processed attractions table, deduplication or additional POI sources.
The metadata CSV is the single source of truth; joins use exact facility_type + facility_domain_code.
REVIEW is never automatically promoted. Missing rules become UNMAPPED, never implicitly included/excluded.
Total source rows: 20451. Source/interim SHA-256: `ea434b071e1c0ac25ba147dafe317514836f7ad5246c4e19ab5a651ca4805775`.
Rule SHA-256: `a32c10136d9177d33003120bdd025e1ee10755aec025e3f0ab99e836f4d65df6`.

## Decision accounting

| decision | row_count |
| --- | --- |
| INCLUDE | 2901 |
| REVIEW | 5790 |
| EXCLUDE | 11760 |
| UNMAPPED | 0 |

## Included subtypes

| facility_type | facility_domain_code | facility_domain_label | row_count | decision | reason | example_names |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 1 | Park | 1274 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["CENTRAL PARK", "RIVERSIDE PARK DOG RUN W 105 ST", "PROSPECT PARK LULLWATER", "JHS 45 RECREATION AREA", "CALVERT VAUX PARK"] |
| 4 | 8 | Sports | 654 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["WINGATE PARK TRACK", "EAST RIVER FIELDS", "PINK PLAYGROUND HANDBALL COURT", "FABER PARK COURTS", "NORTHERN PLAYGROUND BASEBALL FIELD"] |
| 4 | 12 | Garden | 341 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["ST JOHN CANTIUS PARISH COMMUNITY GARDEN", "OASIS COMMUNITY GARDEN", "KEAP FOURTH COMMUNITY GARDEN", "FLORAL VINEYARD GARDEN", "DISCOVERY COMMUNITY GARDEN 2"] |
| 3 | 3 | Theater/Concert Hall | 179 | INCLUDE | Visitor-oriented cultural subtype documented by the source. | ["AMC LOEWS BAY TERRACE THEATRE", "ACTORS TEMPLE THEATRE", "CMX CINEMA E 62 ST", "CIRCLE IN THE SQUARE THEATER", "AMC MAGIC JOHNSON HARLEM 9 THEATRE"] |
| 13 | 2 | Point of Interest | 135 | INCLUDE | Source-designated landmark or point of interest; individual records still require inspection. | ["PELHAM BAY PARK GLOVERS ROCK", "GIOVANNI DA VERRAZZANO MONUMENT", "BRIGADIER GENERAL WINFIELD SCOTT HANCOCK MONUMENT", "LOUISE NEVELSON PLAZA", "CASTLE WILLIAMS"] |
| 4 | 6 | Zoo | 109 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["BRONX ZOO - MADAGASCAR", "BRONX ZOO CHILDRENS ZOO", "STATEN ISLAND ZOO", "BRONX ZOO WORLD OF BIRDS", "PROSPECT PARK ZOO SEA LION STORE & CAFE"] |
| 3 | 4 | Museum | 95 | INCLUDE | Visitor-oriented cultural subtype documented by the source. | ["SKYSCRAPER MUSEUM", "NEW YORK CITY POLICE MUSEUM", "BROOKLYN MUSEUM OF ART", "DYCKMAN HOUSE MUSEUM", "WYCKOFF HOUSE"] |
| 4 | 4 | Beach | 49 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["ARBUTUS BEACH", "ROCKAWAY BEACH & BOARDWALK", "SILVER BEACH", "SEA GATE BEACH", "HALLETTS COVE BEACH"] |
| 13 | 1 | Official Landmark | 37 | INCLUDE | Source-designated landmark or point of interest; individual records still require inspection. | ["SAMUEL J TILDEN HOUSE", "TIMES SQUARE TOWER", "WYCKOFF BENNETT HOMESTEAD", "DAKOTA APARTMENTS", "CHANIN BUILDING"] |
| 4 | 5 | Botanical Garden | 21 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["BK BOTANIC GARDEN ADMIN BUILDING", "ENID A HAUPT CONSERVATORY", "SNUG HARBOR NORTH GATE", "BROOKLYN BOTANICAL GARDEN - TROPICAL PAVILION", "QUEENS BOTANICAL GARDEN EDUCATION BUILDING"] |
| 4 | 2 | Amusement Park | 7 | INCLUDE | Visitable recreational subtype; individual features and constituents still require inspection. | ["CONEY ISLAND LUNA PARK", "THE CYCLONE ROLLER COASTER", "DENOS WONDER WHEEL AMUSEMENT PARK", "B&B CAROUSEL", "ADVENTURERS AMUSEMENT PARK"] |

Included broad facility types:
| facility_type_label | count | percentage |
| --- | --- | --- |
| Recreational Facility | 2455 | 84.62599103757326 |
| Cultural Facility | 274 | 9.445018958979661 |
| Miscellaneous | 172 | 5.928990003447087 |

## Review subtypes

| facility_type | facility_domain_code | facility_domain_label | row_count | decision | reason | example_names |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | 1 | Church | 1321 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["HUNGARIAN REFORMED CHURCH", "LITTLE WIDOWS MITE BAPTIST CHURCH", "SHRINE CHURCH OF ST BERNADETTE", "BETHEL PRESBYTERIAN REFORMED CHURCH", "TIMES SQUARE CHURCH"] |
| 4 | 9 | Playground | 1031 | REVIEW | Recreational subtype may be local-use, restricted or constituent facilities; inspect before promotion. | ["HAROLD SCHNEIDERMAN PLAYGROUND", "BENSONHURST PARK PLAYGROUND", "SUNNERS PLAYGROUND", "CRACK IS WACK PLAYGROUND", "SOUTH OXFORD PARK"] |
| 6 | 8 | Bridge | 954 | REVIEW | Transport or waterfront feature may have visitor interest; accessibility and itinerary suitability are unresolved. | ["HHP OVER AMTRAK AT WEST   96 ST", "59 BR RAMP QNBD TO 21 OV 22", "6 AVENUE OVER LIRR ATLNTC AVE", "CORTELYOU RD OV NYCTA BRIGHTON", "MTR PKWY PED BR OV HOLLIS CRT BL"] |
| 4 | 10 | Other | 461 | REVIEW | Recreational subtype may be local-use, restricted or constituent facilities; inspect before promotion. | ["BILL RAINEY PARK COMFORT STATION", "FOREST PARK BUDDY MONUMENT", "PROSPECT PARK MAINTENANCE FACILITY", "MOSHOLU PLAYGROUND COMFORT STATION", "ST JOHNS PARK COMFORT STATION"] |
| 13 | 4 | Other | 274 | REVIEW | Miscellaneous subtype is ambiguous; cemetery/morgue and other features are not automatically included. | ["BATTERY PARK CITY GATEWAY PLAZA", "US POWERGEN WATER STORAGE TANK", "CON ED PIPE YARD OFFICE", "SEPTEMBER 11 MEMORIAL VENT STRUCTURE SOUTH", "WESTERN UNION INTERNATIONAL PLAZA"] |
| 13 | 5 | UNKNOWN_UNDOCUMENTED | 220 | REVIEW | Source dictionary does not document this exact type/domain pair; preserve for manual review without guessing a subtype. | ["GLENDALE VETERANS TRIANGLE", "LAFAYETTE SQUARE", "COPERNICUS TRIANGLE", "WELLBROCK TRIANGLE", "ALEXANDER GREY TRIANGLE"] |
| 3 | 2 | Library | 217 | REVIEW | Cultural facility may be visitable, but this subtype is not clearly an itinerary attraction without inspection. | ["MOSHOLU LIBRARY", "VAN NEST LIBRARY", "BAISLEY PARK LIBRARY", "HARLEM LIBRARY", "POPPENHUSEN LIBRARY"] |
| 12 | 5 | Other | 208 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | ["CENTRAL PARK RESERVOIR SE", "WINHOLE HASSOCK", "THE NARROWS", "WAYS REEF", "HEEL TAP ROCK"] |
| 9 | 2 | Synagogue | 191 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["SONS JUDAH CONGREGATION", "RIVERDALE TEMPLE", "TEMPLE ISRAEL REFORM CONGREGATION", "AGUDATH ISRAEL OF STATEN ISLAND", "WEST SIDE INSTITUTIONAL SYNAGOGUE"] |
| 6 | 7 | Pier | 158 | REVIEW | Transport or waterfront feature may have visitor interest; accessibility and itinerary suitability are unresolved. | ["PIER 13", "PIER 6 SHEEPSHEAD BAY", "INDIA ST PIER", "AMERICAN VETERANS MEMORIAL PIER", "GOVERNORS ISLAND YANKEE PIER"] |
| 13 | 3 | Cemetery/Morgue | 114 | REVIEW | Miscellaneous subtype is ambiguous; cemetery/morgue and other features are not automatically included. | ["ZION EPISCOPAL CHURCH CEMETERY", "CYPRESS HILLS CEMETERY", "JUNIPER VALLEY PARK PULLIS FARM CEMETERY", "GRACE CHURCH CEMETERY", "SOUTHSIDE BURIAL GROUND"] |
| 4 | 7 | Recreational Center | 92 | REVIEW | Recreational subtype may be local-use, restricted or constituent facilities; inspect before promotion. | ["RIVERBANK PARK CULTURAL BUILDING", "COLUMBUS PARK COMFORT STATION 1", "HOWARD PLAYGROUND COMFORT STATION", "HAFFEN PARK FIELD HOUSE", "CAROLYN MCLAUGHLIN COMMUNITY CENTER"] |
| 7 | 1 | Center | 73 | REVIEW | Market or commercial center may have visitor interest; ordinary retail is not automatically an attraction. | ["THE SHOPS AT COLUMBUS CIRCLE", "BARTOW MALL SHOPPING CENTER", "WTC COMPLEX", "DREISER MALL", "OCULUS SHOPPING MALL"] |
| 3 | 5 | Other | 68 | REVIEW | Cultural facility may be visitable, but this subtype is not clearly an itinerary attraction without inspection. | ["ITALIAN CULTURAL INSTITUTE", "RIVERDALE YMHA YWHA", "92 ST YMYWHA", "AMERICAS SOCIETY ART GALLERY", "DIA ART FOUNDATION BEACON GALLERY"] |
| 6 | 2 | Ferry landing/terminal | 54 | REVIEW | Transport or waterfront feature may have visitor interest; accessibility and itinerary suitability are unresolved. | ["NORTH COVE FERRY LANDING", "MANHATTAN CRUISE TERMINAL", "NY FAST FERRY", "ASTORIA FERRY LANDING", "HOWLAND HOOK MARINE TERMINAL"] |
| 6 | 6 | Marina | 53 | REVIEW | Transport or waterfront feature may have visitor interest; accessibility and itinerary suitability are unresolved. | ["SEA TRAVELERS MARINA", "W 72 ST MARINA", "WEST 79 ST BOAT BASIN", "DIMEGLIO DAN MARINA", "HUDSON RIVER PARK BOATHOUSE"] |
| 4 | 11 | Pool | 50 | REVIEW | Recreational subtype may be local-use, restricted or constituent facilities; inspect before promotion. | ["ALBERT J PARHAM PLAYGROUND POOL", "KOSCIUSZKO POOL", "COMMODORE BARRY POOL", "MARCUS GARVEY POOL", "FREDERICK DOUGLASSPLAYGROUND MINI POOL"] |
| 7 | 3 | Market | 47 | REVIEW | Market or commercial center may have visitor interest; ordinary retail is not automatically an attraction. | ["BK WHOLESALE MEAT MARKET BLDG B", "BROOKLYN TERMINAL MARKET", "ESSEX MARKET", "BRKLYN TERM MKT", "CHELSEA MARKET"] |
| 9 | 6 | Other | 40 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["GRACE MEMORIAL HOUSE", "MANHATTAN JEWISH EXPERIENCE", "SKVER YESHIVA BROOKLYN", "JEHOVAHS WITNESS KINGDOM HALL FLUSHING", "QUEEN OF PEACE RECTORY"] |
| 12 | 1 | Island | 31 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | ["BLAUZES ISLANDS", "GIANT BAR MARSH", "EAST HIGH MEADOW ISLAND", "HART ISLAND", "LIBERTY ISLAND"] |
| 3 | 1 | Center | 29 | REVIEW | Cultural facility may be visitable, but this subtype is not clearly an itinerary attraction without inspection. | ["CENTER FOR JEWISH HISTORY", "GREENWICH VILLAGE CENTER", "PERELMAN PERFORMING ARTS CENTER", "GUGGENHEIM BANDSHELL", "POLICE ATHLETIC LEAGUE WYNN CENTER"] |
| 12 | 6 | Pond | 23 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | ["CENTRAL PARK CONSERVATORY WATER", "GOLDEN POND", "ALLEY POND", "WOLFES POND", "CENTRAL PARK THE POND"] |
| 4 | 3 | Golf Course | 22 | REVIEW | Recreational subtype may be local-use, restricted or constituent facilities; inspect before promotion. | ["MOSHOLU GOLF COURSE", "GOLF DRIVING RANGE AT GATEWAY", "DYKER BEACH PARK JUNIOR GOLF CENTER", "CHELSEA PIERS GOLF CLUB", "BALLYS GOLF LINKS AT FERRY POINT"] |
| 12 | 3 | Lake | 20 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | ["FLUSHING MEADOW PARK WILLOW LAKE", "THE CLOVE LAKE", "KISSENA LAKE", "SWAN BOAT LAKE", "MEADOW LAKE"] |
| 9 | 3 | Temple | 17 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["LIGHT IN THE DARK CHRISTIAN CENTER", "VILLAGE TEMPLE", "FIRST TEMPLE HOUSE OF DAVID", "UNION TEMPLE BROOKLYN", "WEST END TEMPLE"] |
| 9 | 4 | Convent/Monastery | 9 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["OUR LADY QUEEN OF PEACE CONVENT", "ST JOSEPH ST THOMAS PARISH", "ST FRANCIS OF ASSISI CHURCH", "ST TERESAS CONVENT", "OL MT CARMEL CONVENT"] |
| 9 | 5 | Mosque | 8 | REVIEW | Religious site may have cultural visitor interest, but public access and visitor suitability require inspection. | ["BOSNIAN HERCEGOVINIAN ISLAMIC CENTER", "MASJID AR RAHMAN MOSQUE QUEENS VILLAGE", "ISLAMIC CULTURAL CENTER RIVERSIDE DRIVE", "MASJID BAIT UL TAHIR", "MUSLIM CENTER OF MANHATTAN"] |
| 12 | 2 | River | 5 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | ["EAST RIV", "ELIZABETH RIVER", "BRONX RIVER", "HUDSON RIVER", "RAHWAY RIVER"] |
| 12 | 4 | Stream | 0 | REVIEW | Natural water feature may have scenic interest, but a feature label alone does not establish visitable access. | [] |

## Excluded subtypes

| facility_type | facility_domain_code | facility_domain_label | row_count | decision | reason | example_names |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | Public Housing Development | 2608 | EXCLUDE | Residential is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["BETANCES 4 HOUSES BUILDING 8", "DOUGLASS II HOUSES BUILDING 2", "SEDGWICK HOUSES BUILDING 6", "OCEAN BAY (BAYSIDE) BLDG 4", "SUMNER HOUSES BUILDING 11"] |
| 5 | 2 | Day Care Center | 875 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["KINGS BAY YM-YWHA NURSERY ANNEX", "LA ESCUELITA DE SOFIA BILINGUAL DAY CARE", "MARTIN LUTHER KING JR MEMORIAL DAY CARE CENTER", "BARNARD COLLEGE CENTER FOR TODDLER DEVLOPMENT", "HOLMES TOWERS-EISMAN DAY NURSERY"] |
| 2 | 7 | Post Secondary Degree Granting Institution | 842 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["MARITIME COLLEGE OIL PUMP HOUSE", "ST AUGUSTINE HALL", "COLUMBIA UNIVERSITY PUPIN HALL", "NEW YORK UNIVERSITY COLLEGE OF ARTS & SCIENCE", "COLLEGE OF STATEN ISLAND WORLD LANGUAGES & LITERATURE"] |
| 2 | 1 | Public Elementary School | 745 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["EMBER CHARTER SCHOOL FOR MINDFUL EDUCATION INNOVATION & TRANSFORMATION", "PS 59 THE HARBOR VIEW SCHOOL", "PS 239", "THURGOOD MARSHALL ACADEMY LOWER SCHOOL", "ZETA BRONX TREMONT PARK LOWER ELEMENTARY SCHOOL"] |
| 6 | 11 | Water Navigation | 584 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["NEWARK BAY CHANNEL LIGHTED BUOY 10", "BAYONNE TERMINAL CHANNEL LIGHTED BUOY 1", "AMBROSE CHANNEL LIGHTED GONG BUOY 21", "BAYONNE TERMINAL CHANNEL LIGHTED BUOY 2", "FLUSHING BAY LIGHT 8"] |
| 2 | 3 | Public High School | 469 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["ESSEX STREET ACADEMY", "URBAN ASSEMBLY SCHOOL OF DESIGN AND CONSTRUCTION", "HIGH SCHOOL FOR ENTERPRISE, BUSINESS & TECHNOLOGY", "SUSAN E WAGNER HIGH SCHOOL", "HIGH SCHOOL FOR MATHEMATICS SCIENCE & ENGINEERING AT CITY COLLEGE"] |
| 1 | 2 | Private Development | 385 | EXCLUDE | Residential is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["RITZ TOWER BUILDING", "CO-OP CITY BUILDING 26", "CO-OP CITY BUILDING 1", "CO-OP CITY BUILDING 34", "CO-OP CITY ADLER PLACE TOWN HOUSES @ 5 TO 10 ADLER PL"] |
| 7 | 4 | Hotel/Motel | 363 | EXCLUDE | Ordinary commercial business, restaurant, hotel or other commercial facility is outside this attraction pool. | ["THE STANDARD HOTEL EAST VILLAGE", "REDBURY HOTEL", "BELNORD HOTEL", "WASHINGTON JEFFERSON HOTEL", "NOVA GOTHAM HOTEL"] |
| 2 | 2 | Public Junior High-Intermediate-Middle | 354 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["JHS 88 PETER ROUGET", "MS 324 PATRIA MIRABAL", "PS 9 WALTER REED", "EXCEL CHARTER SCHOOL", "MS 328 COMMUNITY MATH & SCIENCE PREP"] |
| 7 | 2 | Business | 309 | EXCLUDE | Ordinary commercial business, restaurant, hotel or other commercial facility is outside this attraction pool. | ["SHELL BANK YACHT CLUB", "QUADROZZI CONCRETE CORPORATION", "FALCO CONSTRUCTION", "VANBRO MOTORS", "PRATT INDUSTRIES PAPER MILLS"] |
| 2 | 4 | Private/Parochial Elementary School | 284 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["ST CHARLES BOROMEO SCHOOL", "ST BARNABAS ELEMENTARY SCHOOL", "BAY RIDGE CHRISTIAN ACADEMY", "ST JOHNS LUTHERAN SCHOOL", "JEWISH FOUNDATION SCHOOL STATEN ISLAND"] |
| 5 | 3 | Adult Day Care | 257 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["CORSI SENIOR CENTER", "BLOOMINGDALE FAMILY PROGRAM HEAD START", "KING TOWERS SENIOR CENTER", "DELLAMONICA STEINWAY SENIOR CENTER", "MARIEN HEIM TOWER & SENIOR CENTER"] |
| 8 | 1 | Government Office | 250 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["HRA CASA OFFICE", "SOCIAL SECURITY 163 ST", "SOCIAL SECURITY CARD CENTER", "BROOKLYN COMMUNITY BOARD 18", "INSPECTOR GENERAL OFFICE"] |
| 8 | 4 | Consulate | 226 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["SUDAN CONSULATE & MISSION TO UN", "BELIZE MISSION TO UN", "MEXICO CONSULATE", "SAUDI ARABIA CONSULATE", "NEPAL MISSION TO THE UN"] |
| 8 | 3 | Post Office | 182 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["STAPLETON POST OFFICE", "KINGSBRIDGE POST OFFICE", "CONEY ISLAND POST OFFICE", "ELTINGVILLE POST OFFICE", "CANAL STREET POST OFFICE"] |
| 8 | 7 | Other | 167 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["DSNY GARAGE MANHATTAN 9", "EGYPT CONSULATE ECONOMIC & COMMERCIAL OFFICE", "HOLY SEE MISSION TO UN", "JAMAICA MISSION TO UN", "DSNY GARAGE QUEENS EAST 7"] |
| 2 | 10 | Public K-8 | 163 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["SUCCESS ACADEMY HARLEM 3 LOWER", "THE SEEALL ACADEMY", "PS/IS 155 NICHOLAS HERKIMER", "ACHIEVEMENT FIRST ASPIRE CHARTER SCHOOL", "SUCCESS ACADEMY CHARTER SCHOOL - NYC 5"] |
| 2 | 6 | Private/Parochial High School | 160 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["TOTTENVILLE HIGH SCHOOL", "ST PETERS BOYS HS", "ST JOSEPH HILL ACADEMY", "BNOT CHAYA ACADEMY", "ST RAYMOND ACADEMY FOR GIRLS"] |
| 10 | 1 | Hospital | 156 | EXCLUDE | Health Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["JACOBI MEDICAL CENTER HELIPAD", "LENOX HEALTH GREENWICH VILLAGE", "WEILL CORNELL PSYCHIATRY SPECIALTY CENTER", "BRONX PSYCHIATRIC CENTER CENTRAL SERVICES BUILDING", "BRONX-LEBANON LIFE RECOVERY CENTER"] |
| 5 | 6 | Other | 156 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["LENOX HILL NEIGHBORHOOD HOUSE HEADQUARTERS", "SAINT JOHNS RESIDENCE FOR BOYS", "ISRAEL SENIOR HOUSING", "MERCY FIRST ANGEL GUARDIAN CAMPUS", "POMONOK HOUSES COMMUNITY CENTER"] |
| 2 | 16 | Private/Parochial K-8 | 154 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["PARKWAY ELEMENTARY SCHOOL", "SPEYER LEGACY SCHOOL", "KINNERET DAY SCHOOL", "HOLY TRINITY CATHOLIC ACADEMY", "YESHIVA TIFERETH MOSHE"] |
| 11 | 6 | FDNY Engine Company | 152 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["ENGINE 62 LADDER 32", "ENGINE 229 LADDER 146", "ENGINE 67", "ENGINE 319", "ENGINE 72"] |
| 5 | 4 | Nursing Home/Assisted Living Facility | 141 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["HEBREW HOME AT RIVERDALE", "BENSONHURST CENTER FOR REHABILITATION & HEALTHCARE", "FINDLAY HOUSE", "PARKER JEWISH INSTITUTE FOR HEALTH CARE AND REHABILITATION", "BAINBRIDGE NURSING & REHABILITATION CENTER"] |
| 7 | 5 | Restaurant | 119 | EXCLUDE | Ordinary commercial business, restaurant, hotel or other commercial facility is outside this attraction pool. | ["PIER A HARBOR HOUSE", "CROSS BAY DINER", "GIANDO ON THE WATER", "PIER I CAFE", "TONYS PIER RESTAURANT"] |
| 2 | 13 | Public School Building | 103 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["PETRIDES SCHOOL BUILDING C", "ALTERNATE LEARNING CENTER THOMPKINS PARK", "ALTERNATE LEARNING CENTER CLOISTERS", "GREAT KILLS HIGH SCHOOL BUILDING", "SKILLMAN HIGH SCHOOL BUILDING"] |
| 7 | 6 | Other | 99 | EXCLUDE | Ordinary commercial business, restaurant, hotel or other commercial facility is outside this attraction pool. | ["WALL STREET PLAZA", "FT SCHUYLER", "BROOKLYN NAVY YARD - BUILDING 292", "BROOKLYN NAVY YD BLDG 313 (OLD)", "CALIENTE CAB RESTAURANT 7 AVE S"] |
| 11 | 10 | NYPD Other | 95 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["PSA 3 SATELLITE OFFICE", "NYPD HIGHWAY UNIT 3 STATION", "OLD POLICE ACADEMY", "TBPD DIST 34", "EMERGENCY SERVICE UNIT 2"] |
| 2 | 12 | Public Secondary School | 88 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["BROOKLYN SECONDARY SCHOOL FOR COLLABORATIVE STUDIES", "THE URBAN ASSEMBLY BRONX ACADEMY OF LETTERS", "PARK SLOPE COLLEGIATE SECONDARY SCHOOL", "BROOKLYN COLLEGIATE A COLLEGE BOARD SCHOOL", "NEW HEIGHTS ACADEMY CHARTER SCHOOL"] |
| 2 | 17 | Private/Parochial K-12 all grades | 84 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["UNITED TALMUDICAL ACADEMY GIRLS 14 AV", "THE LIFE SKILLS SCHOOL", "HORACE MANN SCHOOL ALUMNI FIELD", "BNOS MENACHEM SCHOOL", "YESHIVA & MESIVTA TORAH TEMIMAH"] |
| 11 | 1 | NYPD Precinct | 81 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["41 PRECINCT", "49 PRECINCT", "73 PRECINCT", "33 PRECINCT", "108 PRECINCT"] |
| 11 | 12 | FDNY Other | 81 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["FDNY EMS STATION 40", "EMS HQ", "FDNY ACADEMY TAXPAYER", "FDNY EMS STATION 7", "FDNY ACADEMY MASK SERVICE UNIT"] |
| 2 | 15 | Private/Parochial Early Childhood | 80 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["WILLIAM WOODWARD JR NURSERY SCHOOL", "WESTSIDE MONTESSORI SCHOOL", "LEMAN MANHATTAN PREPARATORY LOWER SCHOOL", "SALVE REGINA CATHOLIC ACADEMY LOWER SCHOOL", "PARKSIDE SCHOOL"] |
| 10 | 4 | Other | 60 | EXCLUDE | Health Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["NEW YORK PRESBYTERIAN HOSPITAL ALLEN HOSPITAL", "CREEDMOOR HOSPITAL", "PARK SLOPE NEIGHBORHOOD FAMILY CENTER", "PHILLIPS BETH ISRAEL SCHOOL OF NURSING", "NYS OMH POWER PLANT"] |
| 5 | 5 | Homeless shelter | 60 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["STADIUM WOMENS SHELTER", "JAMAICA ARMORY SHELTER FOR WOMEN", "CAMBRIDGE HOTEL", "SAMARITAN VILLAGE FORBELL MENS SHELTER", "LAGUARDIA FAMILY CENTER"] |
| 11 | 4 | FDNY Battalion | 54 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["BATTALION 37 ENGINE 222", "BATTALION 48 ENGINE 240", "BATTALION 43 ENGINE 245 LADDER 161", "FDNY EMS STATION 3", "BATTALION 27 ENGINE 79 LADDER 37"] |
| 8 | 6 | Military | 54 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["FT HAMILTON COMMUNITY CLUB", "369 REGIMENT ARMORY", "US COAST GUARD MANHATTAN STATION", "FT HAMILTON BOWLING CENTER", "MULLER ARMY RESERVE CNTR"] |
| 11 | 7 | FDNY Special Unit | 52 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["FDNY PURPLE K 84", "FDNY BRUSH FIRE UNIT 2", "SATELLITE 2 FDNY", "FDNY RAC UNIT 4", "FDNY RAC UNIT 2"] |
| 6 | 12 | Other | 51 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["PATH STATION 33 STREET", "FEDERAL PARKING HOWARD STREET GARAGE", "CABLE SECTION BROOKLYN", "MIRAMAR YACHT CLUB", "SOUTH ST SHIPYARD"] |
| 10 | 3 | Outpatient care center/Clinic | 50 | EXCLUDE | Health Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["DANIEL WEBSTER  HOUSES CHILD HEALTH CENTER", "ST BARNABAS AMBULATORY CARE CENTER", "MT SINAI KIDNEY CENTER EAST RIVER PLAZA", "STAPLETON FAMILY HEALTH CLINIC", "PARKMED PHYSICIANS"] |
| 6 | 3 | Transit/Maintenance Yard | 48 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["NYCTA UNIONPORT YARD", "FRESH POND YARD", "BUSHWICK YARD", "MTA YUKON BUS DEPOT", "ARCH STREET YARD"] |
| 2 | 9 | Public Early Childhood | 47 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["PS 222 FIRE FIGHTER CHRISTOPHER A SANTORA SCHOOL", "ZETA BRONX MOUNT EDEN EARLY CHILDHOOD SCHOOL", "PS 583", "PS 326", "DISTRICT 29 PRE-K CENTER JAMAICA AVE"] |
| 6 | 4 | Airport | 42 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["JFK BUILDING 287", "JFK BUILDING 288", "LGA HANGAR 5B", "JFK BUILDING 245C", "JFK TERMINALS 1 2 3 GAR"] |
| 2 | 14 | Public School Annex | 41 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["PS 279 ANNEX", "PS 230 ANNEX", "PS 1 ANNEX", "PS 33 ANNEX", "PS 36 ANNEX"] |
| 2 | 5 | Private/Parochial Junior/Middle School | 39 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["LITTLE RED SCHOOL HOUSE", "HORACE MANN SCHOOL SPENCE COTTAGE", "ST PATRICK CATHOLIC ACADEMY", "RODEPH SHOLOM SCHOOL 84 ST", "CITY KNOLL MIDDLE SCHOOL"] |
| 11 | 11 | Other | 38 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["STA 29 (543-7340)", "FULTON COMMUNITY CORRECTIONAL FACILITY", "GLEN OAKS VOLUNTEER AMBULANCE CORPS", "METROPOLITAN DETENTION CENTER", "BRAVO VOLUNTEER AMBULANCE SERVICE"] |
| 8 | 2 | Court of law | 36 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["US BANKRUPTCY COURT", "CRIMINAL COURT HOUSE", "MANHATTAN FAMILY COURT", "RICHMOND COUNTY SUPREME COURT RICHMOND TER", "CIVIL COURT"] |
| 2 | 11 | Public  K-12 all grades | 34 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["ACHIEVEMENT FIRST APOLLO CHARTER SCHOOL", "PS 596", "PS 141", "KESWELL SCHOOL", "PS 176"] |
| 11 | 8 | FDNY Division | 32 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["DIVISION 8 ENGINE 160 RESCUE 5", "FDNY EMS STATION 49", "DIVISION 6 ENGINE 71 LADDER 55", "EMS DIV 6", "FDNY EMS STATION 13"] |
| 1 | 5 | Other | 31 | EXCLUDE | Residential is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["21 PENN PLAZA", "EINSTEIN COLLEGE EASTCHESTER ROAD RESIDENCE COMPLEX", "STUYVESANT TOWN 521 E 14 523 E 14 525 E 14", "CARLTON HOUSE", "PILOT COVE MANOR APARTMENTS"] |
| 6 | 1 | Bus Terminal | 31 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["GEORGE WASHINGTON BRIDGE BUS TERMINAL", "BUSH TERMINAL", "MTA E NEW YORK DEPOT", "MTA QUEENS VILLAGE BUS DEPOT", "PENN STATION WEST END CONCOURSE"] |
| 1 | 4 | Constituent | 29 | EXCLUDE | Residential is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["ROCHDALE VILLAGE BUILDING 19", "ROCHDALE VILLAGE BUILDING 6", "ROCHDALE VILLAGE BUILDING 4", "ROCHDALE VILLAGE BUILDING 15", "QUEENS COURT"] |
| 6 | 9 | Tunnel | 28 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["NORTH RIVER TUNNEL NORTH TUBE", "CLARK STREET TUBE", "PARK", "STEINWAY TUBE", "HOLLAND"] |
| 5 | 1 | Residential Child Care | 21 | EXCLUDE | Social Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["METRO NORTH DAY CARE CENTER", "HAMMEL CHILD CARE CENTER", "ARMSTRONG I HOUSES BLDG 11", "JONATHAN WILLIAMS DAYCARE CENTER", "CHICKPEAS CHILDCARE CENTER"] |
| 11 | 5 | Correctional Facility | 16 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["RIKER'S ISLAND", "GEORGE R VIERNO CENTER", "RIKERS ISLAND WEST FACILITY", "RIKERS ISLAND BEACON", "RIKERS ISLAND POWER HOUSE"] |
| 2 | 8 | Other | 13 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["LINDAMOOD BELL EAST SIDE LEARNING CENTER", "ST JOSEPH HILL ACADEMY MADONNA HALL", "NY CONSERVATORY OF MUSIC", "COLLEGE OF STATEN ISLAND DOLPHIN COVE SOUTH", "URBAN DOVE CHARTER SCHOOL"] |
| 11 | 3 | FDNY Ladder Company | 12 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["LADDER 116", "ENGINE 10 LADDER 10", "LADDER 134", "LAD 42 FDNY\\E 152", "LADDER 31"] |
| 2 | 18 | Private/Parochial Secondary School | 12 | EXCLUDE | Education Facility is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["MARSH AVENUE SCHOOL FOR EXPEDITIONARY LEARNING", "GAYNOR MCCOWN EXPEDITIONARY LEARNING SCHOOL", "ST IGNATIUS LOYOLA SCHOOL", "ST CATHARINE ACADEMY", "SCANLAN HS BUILDING 9 A"] |
| 6 | 5 | Heliport | 6 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | ["WEST 30 STREET VIP HELIPORT", "ONE POLICE PLAZA HELIPORT", "DOWNTOWN MANHATTAN HELIPORT", "NYPD AIR OPERATION HELIPORT (FLOYD BENNETT FIELD)", "EAST 34 ST HELIPORT"] |
| 11 | 9 | FDNY Squad | 5 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["SQUAD 288", "SQUAD 1", "SQUAD 18", "SQUAD 252", "SQUAD 41"] |
| 1 | 1 | Gated Development | 4 | EXCLUDE | Residential is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["BREEZY POINT", "BREEZY POINT ROXBURY", "MILL HARBOR CONDOMINIUMS", "MAGNOLIA COURT"] |
| 10 | 2 | Inpatient care center | 2 | EXCLUDE | Health Services is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | ["MADELINE E RANDERS RESIDENCE SUBSTANCE ABUSE TREATMENT", "NEW YORK CITY CHILDRENS CENTER"] |
| 11 | 2 | NYPD Checkpoint | 0 | EXCLUDE | Public Safety is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | [] |
| 6 | 10 | Exit/Entrance | 0 | EXCLUDE | Ordinary facility or infrastructure is outside the initial itinerary-attraction pool. | [] |
| 8 | 5 | Embassy | 0 | EXCLUDE | Government Facility (non public safety) is excluded by taxonomy in this initial candidate policy; no name-based exceptions. | [] |

## Included borough distribution

| borough | count | percentage |
| --- | --- | --- |
| Manhattan | 995 | 34.29851775249914 |
| Brooklyn | 733 | 25.26714925887625 |
| Queens | 498 | 17.166494312306103 |
| Bronx | 436 | 15.029300241296104 |
| Staten Island | 239 | 8.238538435022406 |

## Included examples

| name | facility_type_label | facility_domain_label | borough | latitude | longitude |
| --- | --- | --- | --- | --- | --- |
| 13TH STREET REPERTORY | Cultural Facility | Theater/Concert Hall | Manhattan | 40.736110037326 | -73.996550343571 |
| 80 ST MARKS THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.727604704549 | -73.985773885068 |
| ACTORS TEMPLE THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.761243249062 | -73.989076555682 |
| AL HIRSCHFELD THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.759281669849 | -73.989225599795 |
| ALAMO DRAFTHOUSE DOWNTOWN BROOKLYN | Cultural Facility | Theater/Concert Hall | Brooklyn | 40.690745086637 | -73.983186810982 |
| ALICE TULLY HALL | Cultural Facility | Theater/Concert Hall | Manhattan | 40.773648480708 | -73.982600645487 |
| ALPINE CINEMAS | Cultural Facility | Theater/Concert Hall | Brooklyn | 40.633612051806 | -74.020662912187 |
| AMBASSADOR THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.761200100252 | -73.985078614344 |
| AMC 19 ST EAST THEATER | Cultural Facility | Theater/Concert Hall | Manhattan | 40.738565793239 | -73.989732500392 |
| AMC BAY PLAZA CINEMA 13 | Cultural Facility | Theater/Concert Hall | Bronx | 40.867014848073 | -73.825009464129 |
| AMC EMPIRE 25 THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.756714418235 | -73.989279973627 |
| AMC KIPS BAY 15 THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.742859539479 | -73.976740655876 |
| AMC LOEWS 84 ST THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.786729623692 | -73.97734215406 |
| AMC LOEWS BAY TERRACE THEATRE | Cultural Facility | Theater/Concert Hall | Queens | 40.77903278126 | -73.778836585245 |
| AMC LOEWS FRESH MEADOWS THEATRE | Cultural Facility | Theater/Concert Hall | Queens | 40.741106191997 | -73.783713641198 |
| AMC LOEWS ORPHEUM THEATER 3 AVE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.779527246734 | -73.954189230643 |
| AMC MAGIC JOHNSON HARLEM 9 THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.809719665283 | -73.951787693064 |
| AMC THEATRE VILLAGE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.731638396974 | -73.988726569776 |
| AMERICAN AIRLINES THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.75683783109 | -73.98807781414 |
| AMERICAN MIME THEATRE | Cultural Facility | Theater/Concert Hall | Manhattan | 40.730765512229 | -73.990243500202 |

## Borderline review examples

| name | facility_type_label | facility_domain_label | borough | latitude | longitude |
| --- | --- | --- | --- | --- | --- |
| ANTHOLOGY FILM ARCHIVES | Cultural Facility | Center | Manhattan | 40.724711215409 | -73.990216765059 |
| BROOKLYN ACADEMY OF MUSIC | Cultural Facility | Center | Brooklyn | 40.686628432349 | -73.977826479352 |
| CENTER FOR BOOK ARTS | Cultural Facility | Center | Manhattan | 40.744818120759 | -73.989894610851 |
| CENTER FOR JEWISH HISTORY | Cultural Facility | Center | Manhattan | 40.738020730734 | -73.993845945899 |
| CHINESE CONSOLIDATED BENEVOLENT ASSOCIATION | Cultural Facility | Center | Manhattan | 40.715931769772 | -73.997956968648 |
| CITY COLLEGE ALUMNI HOUSE | Cultural Facility | Center | Manhattan | 40.822299317026 | -73.948218994423 |
| CROSS ISLAND YMCA | Cultural Facility | Center | Queens | 40.732833403895 | -73.727774825138 |
| DIA ART FOUNDATION CHELSEA GALLERY | Cultural Facility | Center | Manhattan | 40.747853793076 | -74.006169360744 |
| DUMBO ARTS CENTER | Cultural Facility | Center | Brooklyn | 40.702712745015 | -73.989098210347 |
| EDITH AND CARL MARKS JEWISH COMMUNITY HOUSE OF BENSONHURST | Cultural Facility | Center | Brooklyn | 40.606269324129 | -73.989759630892 |
| FLATBUSH PARK JEWISH CENTER | Cultural Facility | Center | Brooklyn | 40.61644328556 | -73.912944519324 |
| FLUSHING TOWN HALL | Cultural Facility | Center | Queens | 40.763824421268 | -73.830101580653 |
| GREENWICH VILLAGE CENTER | Cultural Facility | Center | Manhattan | 40.729405430209 | -73.999625881118 |
| GUGGENHEIM BANDSHELL | Cultural Facility | Center | Manhattan | 40.772491434074 | -73.985686297186 |
| INTEGRATED COMMUNITY CENTER VICTORY BLVD | Cultural Facility | Center | Staten Island | 40.630856363926 | -74.088698386801 |
| JAVITS CENTER | Cultural Facility | Center | Manhattan | 40.757460121442 | -74.003413066772 |
| JENNINGS GALLERY AT KENKELEBA | Cultural Facility | Center | Manhattan | 40.72164720088 | -73.982865443862 |
| KENKELEBA HOUSE | Cultural Facility | Center | Manhattan | 40.721997558915 | -73.982906227577 |
| LINCOLN CENTER | Cultural Facility | Center | Manhattan | 40.773181349034 | -73.983844257009 |
| MANHATTAN BEACH JEWISH CENTER | Cultural Facility | Center | Brooklyn | 40.580444667974 | -73.953908691268 |

## Undocumented taxonomy

UNKNOWN_UNDOCUMENTED rows: 220. Their source subtype labels remain null in facility_domain_label_raw.
The current undocumented pair is type 13/domain 5, classified REVIEW without inventing a meaning.
| facility_type | facility_domain_code | name | borough | latitude | longitude |
| --- | --- | --- | --- | --- | --- |
| 13 | 5 | 16 LINDENS TRIANGLE | Brooklyn | 40.584407929289 | -73.952471019414 |
| 13 | 5 | A PHILIP RANDOLPH SQUARE | Manhattan | 40.803897770197 | -73.9524516225 |
| 13 | 5 | ABE LEBEWOHL TRIANGLE | Manhattan | 40.730088726057 | -73.987791729215 |
| 13 | 5 | ABE WOLFSON TRIANGLE | Queens | 40.728233968752 | -73.815070827978 |
| 13 | 5 | ABINGDON SQUARE | Manhattan | 40.737330475806 | -74.005419707046 |
| 13 | 5 | ADMIRAL TRIANGLE | Brooklyn | 40.676916676515 | -74.001064879386 |
| 13 | 5 | AIMEE TRIANGLE | Brooklyn | 40.61301531589 | -73.944020057838 |
| 13 | 5 | ALBEN TRIANGLE | Brooklyn | 40.639429183356 | -73.994556698351 |
| 13 | 5 | ALEXANDER GREY TRIANGLE | Queens | 40.79519093837 | -73.813751854071 |
| 13 | 5 | ALICE KORNEGAY TRIANGLE | Manhattan | 40.806446575234 | -73.935389080901 |

## Candidate duplicate-name analysis

| metric | value |
| --- | --- |
| unique_candidate_names | 2894 |
| repeated_name_groups | 7 |
| rows_with_repeated_names | 14 |
| same_name_same_coordinates_rows | 0 |
| same_name_different_coordinates_groups | 7 |
| same_name_different_coordinates_rows | 14 |

Exact name/coordinate equality is used; no geographic tolerance, deduplication or canonical identity inference.
## Candidate name inspection

Flagged INCLUDE rows: 121. Flags are exploratory; none are removed.
| name | facility_domain_label | borough | name_review_flags |
| --- | --- | --- | --- |
| COLLEGE POINT MULTIPLEX CINEMA | Theater/Concert Hall | Queens | school_like |
| NEW YORK UNIVERSITY CANTOR FILM CENTER | Theater/Concert Hall | Manhattan | school_like |
| NEW YORK UNIVERSITY FREDERICK LOEWE THEATRE | Theater/Concert Hall | Manhattan | school_like |
| NEW YORK UNIVERSITY PROVINCETOWN PLAYHOUSE | Theater/Concert Hall | Manhattan | school_like |
| PERFORMING GARAGE | Theater/Concert Hall | Manhattan | facility_like |
| ST ANNS WAREHOUSE | Theater/Concert Hall | Brooklyn | facility_like |
| AMSTERDAM DEPOT | Museum | Manhattan | maintenance_service |
| MOMA PS 1 | Museum | Queens | school_like |
| NATIONAL ACADEMY MUSEUM | Museum | Manhattan | school_like |
| TRANSIT MUSEUM GALLERY ANNEX & STORE | Museum | Manhattan | facility_like |
| BAY TERRACE PLAYGROUND COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| BROOKLYN BRIDGE PARK CONSERVANCY BUILDING | Park | Brooklyn | facility_like |
| BUFANO PARK COMFORT STATION | Park | Bronx | maintenance_service;facility_like |
| CAMBRIA PLAYGROUND COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| CENTRAL PARK 79 ST MAINTENANCE YARD | Park | Manhattan | maintenance_service;facility_like |
| CENTRAL PARK ARSENAL BUILDING | Park | Manhattan | facility_like |
| CENTRAL PARK RESERVOIR PUMP HOUSE S | Park | Manhattan | maintenance_service |
| CLOVE LAKES PARK COMFORT STATION | Park | Staten Island | maintenance_service;facility_like |
| CLOVE LAKES PARK GARAGE | Park | Staten Island | facility_like |
| DITMARS PLAYGROUND COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| DR CHARLES R DREW PARK COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| EDERLE TERRACE COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| EDERLE TERRACE STORAGE | Park | Queens | maintenance_service |
| FLUSHING MEADOWS CORONA PARK UTILITY BUILDING | Park | Queens | maintenance_service;facility_like |
| FMCP WORLDS FAIR MARINA UTILITY BUILDING | Park | Queens | maintenance_service;facility_like |
| FOREST PARK GREENHOUSE OFFICE | Park | Queens | office_like |
| GORMAN PLAYGROUND COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| HARVARD YARD | Park | Staten Island | facility_like |
| HELEN MARSHALL PLAYGROUND COMFORT STATION | Park | Queens | maintenance_service;facility_like |
| HIGH ROCK PARK BUILDING A | Park | Staten Island | facility_like |

## Policy limits

Library, cultural center/other, golf courses, playgrounds, pools, recreational centers/other, religious sites,
markets/commercial centers, ferry landings, marinas, piers, bridges, water features and miscellaneous
cemetery/morgue/other remain REVIEW. These are provisional taxonomy decisions, not visitor-quality judgments.
Government and other ordinary facility categories can contain visitor-oriented individual features; inspect exclusion samples before finalizing policy.
Examples use at most five source rows per configured subtype, seeded with 42 after sorting source IDs.
All source identifiers/raw fields are retained. Restaurant inputs and outputs are not touched.
