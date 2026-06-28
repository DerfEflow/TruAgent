# Aerial Building Footprint and Roof Area Estimator: Build Specification

## Purpose

Build a practical API-driven system that estimates building footprint square footage and, where possible, roof area from an address or selected map location.

The system should prioritize efficient, legally cleaner, and geometry-based methods first. AI vision should be used as a fallback or verification layer, not as the primary measuring instrument.

The core principle:

> Use authoritative or open building polygons when available. Use geospatial math to measure. Use aerial imagery and AI only to verify, correct, or fill gaps.

This avoids the common mistake of asking a vision model to “guess” area from an aerial image when a polygon plus proper projection can produce a more defensible measurement.

---

## Executive Summary

The recommended pipeline is:

1. User enters an address.
2. System geocodes the address to latitude/longitude.
3. System retrieves candidate building footprints from the safest available source.
4. System selects the most likely building polygon.
5. System projects the polygon into an area-preserving coordinate system.
6. System calculates footprint area, perimeter, and bounding dimensions.
7. System overlays the polygon on imagery for human verification.
8. System uses AI vision only to inspect the polygon, detect issues, or propose a fallback outline.
9. User can manually correct the outline.
10. System generates an estimate record with source, confidence, assumptions, and warnings.

Primary measurement should come from geometry, not image interpretation.

---

## Key Definitions

## Building Footprint Area

The horizontal ground-level area enclosed by the building outline.

Useful for:

- Approximate building size
- Lead qualification
- Initial material/labor ballpark
- Comparing to parcel/building records
- Flat-roof preliminary estimating

Limitation:

- Does not account for sloped roof planes, overhangs, parapet details, courtyards, canopies, multiple roof levels, or roof equipment areas.

## Roof Area

The actual roof surface area.

For flat commercial roofs, this may be close to footprint area. For pitched roofs, roof area is larger than footprint area because of slope.

Useful for:

- Roofing estimates
- Coating quantities
- Solar calculations
- Drainage planning

Limitation:

- Requires slope, segmentation, roof-plane data, or manual verification for accuracy.

## Confidence Score

A system-generated score based on source quality, polygon alignment, imagery clarity, recency, and user verification.

Do not present early automated measurements as final takeoff values unless manually verified.

---

# Source Priority Ladder

Use data sources in this order.

## Tier 1: Existing Building Footprints

Use existing building-footprint polygons first.

Preferred sources:

1. County or municipal GIS building footprints
2. Microsoft Global ML Building Footprints
3. Microsoft US Building Footprints
4. OpenStreetMap building polygons
5. State GIS repositories
6. Commercial building/parcel datasets

Reason:

- Fast
- Cheap
- Easier to calculate area accurately
- Less legally problematic than tracing from proprietary imagery
- Better foundation for repeatable automation

## Tier 2: Roof or Building Insight APIs

Use APIs that explicitly return building or roof measurements when available.

Candidate:

- Google Solar API buildingInsights

Caution:

- Google Solar API roof segment `areaMeters2` is roof area accounting for tilt, not ground footprint area.
- Coverage may vary.
- Must follow Google Maps Platform terms and applicable API-specific rules.
- Treat returned data as a pre-estimate input unless verified.

## Tier 3: Public Aerial Imagery for Verification

Use public or permissively licensed aerial imagery to verify polygons or support fallback AI segmentation.

Candidate sources:

- USGS NAIP imagery
- USGS National Map imagery
- State orthophoto services
- County GIS imagery services
- Public WMS/WMTS/XYZ tile services where licensing permits the intended use

Reason:

- More appropriate for computer vision fallback
- Can often be cached or processed under clearer public-data terms
- Useful where footprints are missing or stale

## Tier 4: Paid Geospatial Providers

Use paid providers when precision and coverage justify cost.

Candidate categories:

- Commercial aerial imagery
- Parcel/building databases
- Roof measurement APIs
- Orthophoto providers
- Property intelligence APIs

Examples to evaluate:

- Nearmap
- EagleView
- Vexcel
- LightBox
- Regrid
- CoreLogic
- Precisely
- State or regional GIS vendors

Caution:

- Licensing varies.
- Some providers permit viewing but not derived data creation.
- Confirm whether automated extraction, caching, and commercial use are allowed.

## Tier 5: AI Vision Fallback

Use AI vision only when:

- No reliable footprint exists
- Existing footprint appears wrong
- Building has changed recently
- User asks for visual verification
- Imagery shows additions or exclusions not present in polygon data
- Manual correction is needed

AI should produce a proposed polygon, confidence flags, and visible uncertainty. Human correction should remain available.

## Tier 6: Manual Polygon Drawing

Always provide a manual fallback.

The user should be able to:

- Draw a polygon
- Edit vertices
- Snap to right angles
- Split buildings
- Exclude courtyards
- Add canopies
- Remove non-roof structures
- Save the corrected measurement
- Mark the result as verified

Manual correction is the final reliability layer.

---

# Google Usage Guidance

## Recommended Google Uses

Use Google APIs for:

- Address geocoding, if terms fit the product
- Map display, if attribution and terms are followed
- User-facing map interaction
- Optional Solar API calls where available and permitted

## Avoid

Do not build the core commercial measurement engine around:

- Scraping Google Earth
- Downloading Google Maps/Earth screenshots
- Using Google satellite imagery to trace building outlines
- Training, testing, validating, or fine-tuning AI models on Google Maps content
- Creating a derived building-footprint database from Google Maps imagery
- Caching Google imagery beyond what the API terms permit

Reason:

Google Maps Platform terms restrict creating content from Google Maps content, including tracing or digitizing building outlines from Maps satellite imagery. The safest product architecture should avoid deriving building polygons from Google imagery unless explicit permission is obtained.

## Practical Interpretation

Google can be a display and location layer.

Google should not be the hidden raw material for automated polygon extraction unless the applicable terms explicitly allow the intended workflow.

Build the measurement engine around open, public, or properly licensed geospatial data.

---

# Recommended MVP

## MVP Goal

Given an address, return a preliminary building footprint square footage with source, confidence, and a visible overlay for verification.

## MVP User Flow

1. User enters address.
2. App geocodes address.
3. App finds candidate building footprints.
4. App selects the most likely footprint.
5. App calculates:
   - Area in square feet
   - Area in square meters
   - Perimeter
   - Approximate length/width bounding box
6. App displays map imagery with polygon overlay.
7. User accepts or edits polygon.
8. App saves result.
9. App generates an estimate summary.

## MVP Output

```json
{
  "address": "string",
  "coordinates": {
    "lat": 0,
    "lon": 0
  },
  "measurement": {
    "footprint_area_sqft": 0,
    "footprint_area_m2": 0,
    "perimeter_ft": 0,
    "perimeter_m": 0
  },
  "source": {
    "type": "county_gis | microsoft | osm | solar_api | ai_fallback | manual",
    "name": "string",
    "retrieved_at": "ISO timestamp",
    "source_url": "string"
  },
  "confidence": {
    "score": 0,
    "level": "low | medium | high",
    "reasons": []
  },
  "warnings": [],
  "verification_status": "unverified | ai_checked | user_verified"
}
```

---

# System Architecture

## Components

## 1. Address Intake

Responsibilities:

- Accept address
- Accept coordinates
- Accept clicked map point
- Normalize address
- Handle ambiguous addresses
- Store original input

Possible providers:

- Google Geocoding API
- Mapbox Geocoding
- OpenStreetMap Nominatim
- US Census Geocoder
- County GIS locator services

Recommended strategy:

- Start with one reliable geocoder.
- Store geocoder provider and confidence.
- Allow user correction on map.

## 2. Geospatial Data Retriever

Responsibilities:

- Query footprint sources
- Query parcel sources if needed
- Query roof/building APIs if available
- Normalize geometry formats
- Cache source metadata
- Return candidate polygons

Data formats to support:

- GeoJSON
- WKT
- Shapefile
- FlatGeobuf
- GeoPackage
- Esri FeatureServer JSON
- WMS/WMTS metadata where applicable
- PMTiles or vector tiles for local indexes

## 3. Candidate Selector

Responsibilities:

- Identify the correct building footprint
- Rank candidate polygons
- Filter false matches
- Handle multi-building parcels
- Handle apartment/commercial campuses
- Return one or more candidates

Ranking factors:

- Distance from geocoded point
- Whether point falls inside polygon
- Whether polygon intersects parcel
- Polygon size reasonableness
- Address/building attributes if available
- Source priority
- Recency
- User selection

Selection logic:

1. Prefer polygon containing geocoded point.
2. If none contains point, choose nearest polygon within threshold.
3. If multiple polygons exist on parcel, show choices.
4. For commercial/industrial parcels, allow multi-building selection.
5. If confidence is low, ask user to click the correct building.

## 4. Geometry Engine

Responsibilities:

- Validate polygons
- Reproject coordinates
- Calculate area and perimeter
- Simplify geometry for UI
- Preserve full-resolution geometry for measurement
- Handle holes, courtyards, multipolygons

Recommended libraries:

- Python: GeoPandas, Shapely, PyProj, Rasterio
- JavaScript/TypeScript: Turf.js, proj4js, OpenLayers geometry utilities
- Database: PostGIS

Critical rule:

Do not calculate area directly in raw latitude/longitude degrees.

Use an appropriate projected coordinate system.

Recommended approaches:

- For local U.S. work, use State Plane or UTM zone where appropriate.
- For general global work, use local equal-area projection or geography-based area calculation in PostGIS.
- In PostGIS, `ST_Area(geography(geom))` can be used for spheroidal area calculations.

## 5. Imagery Display Layer

Responsibilities:

- Show aerial or map background
- Overlay footprint polygon
- Show measurement labels
- Support vertex editing
- Support source attribution
- Avoid improper storage/use of restricted imagery

Possible display options:

- Google Maps for display only
- Mapbox
- MapLibre with open tiles
- OpenLayers
- Leaflet
- County GIS imagery layers
- USGS imagery layers

Recommended:

- Use MapLibre/OpenLayers if you need maximum control over layers.
- Keep licensing metadata attached to each imagery provider.
- Use public/permissive imagery for AI analysis.

## 6. AI Verification Layer

Responsibilities:

- Inspect visual alignment
- Detect likely missed sections
- Detect shadows, tree cover, obstructions
- Identify confidence issues
- Propose fallback outline from permitted imagery
- Explain uncertainty to user

AI should not silently replace geometry.

AI output should be treated as:

- Advisory
- Visual QC
- Fallback outline
- Confidence explanation

## 7. Manual Correction Layer

Responsibilities:

- Let user edit polygons
- Add/remove vertices
- Draw new polygons
- Split/merge polygons
- Exclude areas
- Add separate roof sections
- Save verified geometry

Manual correction should be easy and fast, because automated sources will sometimes be wrong.

## 8. Report Generator

Responsibilities:

- Generate measurement report
- Include source and confidence
- Include warnings
- Include map overlay screenshot if licensing permits
- Include polygon coordinates or simplified geometry
- Include user verification status

Do not include restricted map imagery in reports unless provider terms permit it.

---

# Data Source Connectors

## County GIS Connector

County GIS is often the best source for local commercial work.

## Capabilities

- Search parcel by address
- Retrieve parcel polygon
- Retrieve building footprint polygon if available
- Retrieve owner/building attributes if public
- Retrieve orthophoto layers if permitted
- Retrieve roof/building records where available

## Implementation Notes

Many counties expose Esri FeatureServer endpoints.

Example connector functions:

```ts
type CountyGISConnector = {
  searchAddress(address: string): Promise<AddressCandidate[]>;
  getParcelByPoint(lat: number, lon: number): Promise<ParcelCandidate[]>;
  getBuildingFootprintsByParcel(parcelId: string): Promise<FootprintCandidate[]>;
  getBuildingFootprintsNearPoint(lat: number, lon: number, radiusMeters: number): Promise<FootprintCandidate[]>;
};
```

## Priority

High when available.

Pros:

- Often authoritative
- Local parcel alignment
- May include building attributes
- Often legally cleaner for public records

Cons:

- County-by-county variability
- Different schemas
- Some services are unstable or undocumented
- Coverage varies

---

## Microsoft Building Footprints Connector

## Capabilities

- Load regional building footprint data
- Query by point or bounding box
- Return polygon candidates
- Calculate area locally

## Implementation Strategy

For a production system, do not query the entire raw dataset directly every time.

Recommended options:

1. Preload state/region data into PostGIS.
2. Build spatial indexes.
3. Query by bounding box around geocoded point.
4. Rank candidates.
5. Cache results.

## Suggested Database Table

```sql
CREATE TABLE building_footprints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  source_id TEXT,
  geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
  confidence FLOAT,
  height_m FLOAT,
  area_m2 FLOAT,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP
);

CREATE INDEX idx_building_footprints_geom
ON building_footprints
USING GIST (geom);
```

## Query Example

```sql
SELECT
  id,
  source,
  ST_AsGeoJSON(geom) AS geojson,
  ST_Area(geography(geom)) AS area_m2,
  ST_Distance(
    geography(geom),
    geography(ST_SetSRID(ST_Point(:lon, :lat), 4326))
  ) AS distance_m
FROM building_footprints
WHERE ST_DWithin(
  geography(geom),
  geography(ST_SetSRID(ST_Point(:lon, :lat), 4326)),
  :radius_m
)
ORDER BY
  ST_Contains(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326)) DESC,
  distance_m ASC
LIMIT 10;
```

## Priority

High.

Pros:

- Large coverage
- Openly available
- Fast once indexed locally
- Good fallback where county GIS is missing

Cons:

- Can be outdated
- May miss small structures
- May include false positives
- May not match parcel/address perfectly
- May not distinguish roof sections

---

## OpenStreetMap Connector

## Capabilities

- Query building polygons by point or bounding box
- Retrieve tags
- Use Overpass API or local OSM extracts

## Implementation Strategy

For MVP, Overpass API may be acceptable.

For production, use local OSM extracts or a managed OSM data service.

Example Overpass query concept:

```text
[out:json][timeout:25];
(
  way["building"](around:50, LAT, LON);
  relation["building"](around:50, LAT, LON);
);
out geom;
```

## Priority

Medium.

Pros:

- Open data
- Often good in urban areas
- Includes useful tags in some places

Cons:

- Inconsistent coverage
- Community-generated
- May be incomplete
- Rate limits on public Overpass endpoints
- Requires attribution and license compliance

---

## Google Solar API Connector

## Capabilities

- Request building insights near a location
- Retrieve roof segment areas where available
- Retrieve solar-related building metadata
- Use roof segment area as a supplementary input

## Important Interpretation

`areaMeters2` for roof segments is roof area accounting for tilt, not ground footprint area.

## Recommended Use

Use Solar API as:

- Optional roof-area estimate
- Cross-check against footprint area
- Source for roof segment insights where supported
- Helpful enhancement for residential or solar-compatible buildings

Do not rely on it as the only source for commercial roof takeoffs.

## Priority

Optional.

Pros:

- Can return roof-area-like measurements
- May include roof segment information
- Useful when available

Cons:

- Coverage limitations
- Cost
- API-specific terms
- Not necessarily designed for roof coating estimates
- May not fit all commercial flat-roof use cases

---

## USGS/NAIP Imagery Connector

## Capabilities

- Retrieve public aerial imagery
- Use imagery for visual verification
- Use imagery for AI segmentation fallback where permitted
- Provide non-Google source for computer vision workflows

## Recommended Use

- Verification overlay
- AI segmentation fallback
- Manual correction background
- Audit snapshots where permitted

## Priority

High for AI fallback.

Pros:

- Public imagery
- Broad U.S. coverage
- Useful for permitted computer vision workflows
- Good for avoiding proprietary imagery problems

Cons:

- Resolution and recency vary
- Leaf-on imagery may obscure roofs
- Not always ideal for commercial roofs
- Needs geospatial image handling

---

# Measurement Logic

## Area Calculation Requirements

## Do

- Validate geometry.
- Use projected or geography-aware area calculation.
- Preserve holes in polygons.
- Support multipolygons.
- Return both square meters and square feet.
- Store source geometry separately from user-corrected geometry.
- Record calculation method.

## Do Not

- Calculate area from degrees.
- Let a vision model directly estimate square footage from pixels without scale.
- Treat a screenshot as a reliable measurement source.
- Hide confidence limitations.
- Average multiple sources blindly.

## Unit Conversion

```ts
const SQM_TO_SQFT = 10.76391041671;
const M_TO_FT = 3.280839895;
```

## Geometry Result Schema

```ts
type GeometryMeasurement = {
  areaM2: number;
  areaSqft: number;
  perimeterM: number;
  perimeterFt: number;
  centroid: {
    lat: number;
    lon: number;
  };
  bbox: {
    minLat: number;
    minLon: number;
    maxLat: number;
    maxLon: number;
  };
  calculationMethod:
    | "postgis_geography"
    | "local_equal_area_projection"
    | "state_plane"
    | "utm"
    | "manual_scaled";
};
```

---

# Candidate Confidence Scoring

## Confidence Inputs

Score should consider:

- Source priority
- Source recency
- Whether geocoded point is inside polygon
- Distance from point to polygon
- Whether parcel boundary supports selection
- Polygon size reasonableness
- Presence of multiple nearby buildings
- Imagery alignment
- AI verification result
- User verification status
- Whether polygon was manually edited

## Suggested Scoring

```ts
function scoreCandidate(candidate: Candidate): number {
  let score = 0;

  score += sourceScore(candidate.source);              // 0 to 30
  score += pointRelationshipScore(candidate);          // 0 to 25
  score += recencyScore(candidate);                    // 0 to 10
  score += parcelSupportScore(candidate);              // 0 to 15
  score += imageryAlignmentScore(candidate);           // 0 to 10
  score += userVerificationScore(candidate);           // 0 to 10

  return Math.min(100, Math.max(0, score));
}
```

## Source Score Example

```ts
const sourceScores = {
  user_verified_manual: 30,
  county_building_footprint: 28,
  paid_roof_dataset: 27,
  microsoft_building_footprint: 23,
  osm_building_polygon: 18,
  google_solar_roof_area: 17,
  ai_detected_from_public_imagery: 12,
  rough_manual_box: 8
};
```

## Confidence Labels

```ts
function confidenceLabel(score: number): "low" | "medium" | "high" {
  if (score >= 80) return "high";
  if (score >= 55) return "medium";
  return "low";
}
```

## Warning Examples

- Multiple buildings found near address.
- Geocoded point does not fall inside selected footprint.
- Building footprint source may be outdated.
- Tree cover obscures imagery.
- AI detected possible missed roof section.
- Solar API roof area differs from footprint area by more than threshold.
- Manual verification recommended.
- Imagery source cannot be stored in report under current license.

---

# AI Vision Fallback

## Purpose

Use AI vision to propose or verify building outlines when geometry sources fail.

## Required Inputs

- Legally usable aerial image
- Georeferenced bounds or pixel-to-world transform
- Known coordinate reference system
- User-selected approximate building point
- Optional existing polygon
- Optional parcel boundary

## AI Tasks

The AI may:

- Identify likely roof/building outline
- Detect visible roof sections
- Flag obstructions
- Identify likely courtyard/exclusion areas
- Compare existing polygon to visible roof
- Propose corrections
- Produce a segmentation mask or polygon
- Provide uncertainty notes

## AI Must Not

- Claim final measurement accuracy without scale and geometry
- Use restricted imagery without permission
- Invent hidden roof edges under trees
- Automatically overwrite verified polygons
- Ignore manual user corrections

## Recommended AI Output

```json
{
  "visual_assessment": {
    "outline_alignment": "good | questionable | poor | not_applicable",
    "obstructions": [],
    "possible_missing_sections": [],
    "possible_overincluded_sections": [],
    "confidence": "low | medium | high",
    "notes": []
  },
  "proposed_polygon": {
    "available": false,
    "geojson": null,
    "source": "ai_from_permitted_imagery",
    "requires_user_verification": true
  }
}
```

## Segmentation Methods

Potential approaches:

1. Classical computer vision
   - Edge detection
   - Thresholding
   - Morphological cleanup
   - Hough lines
   - Good only for clear images

2. ML segmentation model
   - SAM-style segmentation
   - Fine-tuned roof/building segmentation
   - Better for complex shapes

3. Vision-language model
   - Good for inspection and explanation
   - Not ideal as sole geometry producer

4. Hybrid
   - Segmentation model creates mask
   - Geometry engine converts mask to polygon
   - Vision model critiques output
   - User verifies

Recommended:

Use hybrid.

---

# Manual Editing UX

## Required Controls

- Add vertex
- Delete vertex
- Drag vertex
- Move polygon
- Split polygon
- Merge polygons
- Add exclusion hole
- Undo/redo
- Snap to right angles
- Show segment lengths
- Show area live
- Select multiple roof sections
- Mark as verified

## Optional Advanced Controls

- Orthogonalize polygon
- Simplify polygon
- Buffer polygon
- Draw rectangle by two corners
- Trace from clicked points
- Lock verified edges
- Compare source vs edited outline

## Verification State

```ts
type VerificationStatus =
  | "unverified"
  | "source_verified"
  | "ai_checked"
  | "user_adjusted"
  | "user_verified"
  | "field_verified";
```

---

# Report Output

## Preliminary Measurement Report

Include:

- Address
- Coordinates
- Map view or non-restricted overlay if permitted
- Footprint area
- Roof area if available
- Perimeter
- Source
- Confidence score
- Verification status
- Warnings
- Assumptions
- Date/time
- User corrections
- Geometry source
- Calculation method

## Report Disclaimer

Suggested language:

```text
This measurement is a preliminary remote estimate derived from available geospatial data and/or permitted imagery. It is not a substitute for field verification, professional roof measurement, or final takeoff. Accuracy may be affected by imagery recency, source data quality, roof overhangs, roof slope, tree cover, shadows, parapets, multiple roof levels, additions, and user-selected boundaries.
```

## Report JSON

```json
{
  "report_type": "preliminary_remote_measurement",
  "address": "",
  "coordinates": {
    "lat": 0,
    "lon": 0
  },
  "areas": {
    "footprint_sqft": 0,
    "footprint_m2": 0,
    "roof_area_sqft": null,
    "roof_area_m2": null
  },
  "perimeter": {
    "feet": 0,
    "meters": 0
  },
  "source_summary": "",
  "confidence": {
    "score": 0,
    "label": "low"
  },
  "verification_status": "unverified",
  "warnings": [],
  "assumptions": [],
  "geometry": {
    "geojson": {}
  }
}
```

---

# Backend Data Model

## Core Tables

## `measurements`

```sql
CREATE TABLE measurements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  address TEXT,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  selected_footprint_id UUID,
  source_type TEXT NOT NULL,
  source_name TEXT,
  area_m2 DOUBLE PRECISION NOT NULL,
  area_sqft DOUBLE PRECISION NOT NULL,
  perimeter_m DOUBLE PRECISION,
  perimeter_ft DOUBLE PRECISION,
  confidence_score INTEGER NOT NULL,
  confidence_label TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  calculation_method TEXT NOT NULL,
  warnings JSONB DEFAULT '[]',
  assumptions JSONB DEFAULT '[]',
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP
);
```

## `measurement_geometries`

```sql
CREATE TABLE measurement_geometries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  measurement_id UUID REFERENCES measurements(id),
  geometry_type TEXT NOT NULL,
  geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_measurement_geometries_geom
ON measurement_geometries
USING GIST (geom);
```

## `source_candidates`

```sql
CREATE TABLE source_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID,
  source_type TEXT NOT NULL,
  source_name TEXT,
  source_id TEXT,
  geom GEOMETRY(MultiPolygon, 4326),
  raw_payload JSONB,
  rank INTEGER,
  confidence_score INTEGER,
  reasons JSONB DEFAULT '[]',
  created_at TIMESTAMP DEFAULT now()
);
```

## `ai_reviews`

```sql
CREATE TABLE ai_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  measurement_id UUID REFERENCES measurements(id),
  model_provider TEXT NOT NULL,
  review_type TEXT NOT NULL,
  input_summary JSONB,
  output JSONB,
  confidence_label TEXT,
  created_at TIMESTAMP DEFAULT now()
);
```

---

# API Design

## Endpoint: Create Measurement Request

```http
POST /api/measurements/estimate
```

Request:

```json
{
  "address": "string",
  "lat": null,
  "lon": null,
  "options": {
    "includeSolarApi": false,
    "includeAiReview": false,
    "preferOpenSources": true,
    "allowExternalImagery": false
  }
}
```

Response:

```json
{
  "request_id": "uuid",
  "status": "candidate_selection_required | estimated | failed",
  "candidates": [],
  "recommended_candidate_id": "uuid",
  "measurement": {}
}
```

## Endpoint: Get Candidates

```http
GET /api/measurements/{requestId}/candidates
```

## Endpoint: Accept Candidate

```http
POST /api/measurements/{requestId}/accept-candidate
```

Request:

```json
{
  "candidate_id": "uuid"
}
```

## Endpoint: Save Manual Geometry

```http
POST /api/measurements/{measurementId}/geometry/manual
```

Request:

```json
{
  "geojson": {},
  "verification_status": "user_verified"
}
```

## Endpoint: AI Visual Review

```http
POST /api/measurements/{measurementId}/ai-review
```

Request:

```json
{
  "imagery_source": "usgs_naip | county_public | user_uploaded | other_permitted",
  "review_existing_polygon": true,
  "allow_polygon_proposal": true
}
```

## Endpoint: Export Report

```http
POST /api/measurements/{measurementId}/report
```

Request:

```json
{
  "format": "json | markdown | pdf",
  "include_map_image": false,
  "include_geojson": true
}
```

---

# Processing Pipeline

## Main Pipeline

```ts
async function estimateBuildingArea(input: EstimateInput): Promise<EstimateResult> {
  const location = await resolveLocation(input);

  const candidates = await collectFootprintCandidates(location);

  const ranked = rankCandidates(candidates, location);

  if (ranked.length === 0) {
    return createFallbackNeededResult(location);
  }

  const selected = ranked[0];

  if (selected.confidenceScore < 55 || ranked.length > 1) {
    return createCandidateSelectionResult(location, ranked);
  }

  const measurement = calculateMeasurement(selected.geometry);

  const confidence = calculateConfidence(selected, measurement);

  return saveMeasurement({
    location,
    selected,
    measurement,
    confidence,
    verificationStatus: "source_verified"
  });
}
```

## Candidate Collection

```ts
async function collectFootprintCandidates(location: Location): Promise<Candidate[]> {
  const results: Candidate[] = [];

  results.push(...await queryCountyGIS(location));
  if (results.some(r => r.sourceType === "county_building_footprint")) {
    return results;
  }

  results.push(...await queryMicrosoftFootprints(location));
  results.push(...await queryOSMBuildings(location));

  return deduplicateCandidates(results);
}
```

## Fallback Pipeline

```ts
async function fallbackWithPermittedImagery(location: Location): Promise<FallbackResult> {
  const imagery = await getPermittedImagery(location);

  if (!imagery) {
    return {
      status: "manual_required",
      reason: "No permitted imagery or footprint source available."
    };
  }

  const aiProposal = await runAiSegmentation(imagery, location);

  return {
    status: "ai_proposal_requires_user_verification",
    proposedPolygon: aiProposal.polygon,
    visualAssessment: aiProposal.assessment
  };
}
```

---

# Frontend Map Requirements

## Recommended Libraries

- MapLibre GL JS
- OpenLayers
- Leaflet with drawing plugins
- Turf.js for lightweight client-side geometry
- deck.gl for advanced overlays if needed

## Required UI States

1. Address entry
2. Location confirmation
3. Candidate footprint selection
4. Measurement preview
5. Polygon edit mode
6. AI review results
7. Final measurement summary
8. Report export

## Map Layers

- Base map
- Aerial imagery
- Parcel boundary, if available
- Source footprint polygon
- User-edited polygon
- AI-proposed polygon
- Exclusion holes
- Segment labels
- Confidence markers

## Visual Style

Suggested polygon styling:

- Source polygon: solid outline
- AI-proposed polygon: dashed outline
- User-edited polygon: highlighted outline
- Exclusion areas: hatched fill
- Low confidence: warning badge
- Verified: check marker

---

# Error Handling

## Common Errors

## Address Not Found

Response:

- Ask user to refine address.
- Allow map click.
- Allow direct coordinates.

## No Building Footprint Found

Response:

- Offer public imagery fallback.
- Offer manual draw mode.
- Try OSM/Microsoft/county sources in different order.
- Increase search radius.

## Multiple Buildings Found

Response:

- Show candidate polygons.
- Ask user to select building.
- Support multi-building selection.

## Polygon Invalid

Response:

- Attempt geometry repair.
- Show warning.
- Ask user to manually correct if repair fails.

## Imagery Restricted

Response:

- Do not process restricted imagery.
- Use display-only mode if allowed.
- Offer public/permitted imagery source.
- Offer manual drawing.

## AI Review Low Confidence

Response:

- Do not auto-apply.
- Show notes.
- Require user verification.

---

# Accuracy and Limitations

## Major Accuracy Risks

- Outdated imagery
- Outdated footprint datasets
- Geocoder placed point on parcel center, not building
- Multiple buildings on one parcel
- Overhangs and canopies
- Courtyards
- Atriums
- Mechanical penthouses
- Multi-level roofs
- Roof slope
- Trees
- Shadows
- White roof on light background
- Black roof on asphalt
- Recent construction
- Demolition
- Poor dataset alignment

## Mitigation

- Show source and recency
- Let user verify polygon
- Cross-check multiple sources
- Use AI visual review
- Flag low confidence
- Keep manual edit tools prominent
- Never hide assumptions
- Preserve source geometry and edited geometry separately

---

# Development Phases

## Phase 1: Geometry-First MVP

Build:

- Address input
- Geocoding
- Microsoft footprint lookup from local indexed data
- OSM fallback
- Area/perimeter calculation
- Basic map overlay
- Candidate selection
- Measurement output JSON

Do not build AI yet.

Success criteria:

- Given an address, system returns candidate footprints.
- User can select footprint.
- System calculates area correctly.
- Output includes source and confidence.

## Phase 2: County GIS and Public Data Connectors

Build:

- County GIS connector pattern
- Esri FeatureServer support
- Parcel lookup by point
- Building footprint lookup by parcel
- Source priority configuration
- Source metadata storage

Success criteria:

- System can use county data where available.
- County footprints outrank general datasets.
- Multiple source candidates are deduplicated.

## Phase 3: Manual Editing and Verification

Build:

- Polygon edit UI
- Vertex editing
- Draw new polygon
- Add exclusion holes
- Live area updates
- Save verified geometry
- Version source vs user-corrected geometry

Success criteria:

- User can correct an automated polygon.
- Corrected geometry recalculates area.
- Verification status is saved.

## Phase 4: AI Visual Review with Permitted Imagery

Build:

- Public/permitted imagery connector
- AI review of existing polygon
- Obstruction detection
- Missed-section warnings
- Optional proposed polygon
- Review panel

Success criteria:

- AI can flag likely alignment issues.
- AI output is advisory.
- AI-proposed polygons require user verification.
- Restricted imagery is not processed.

## Phase 5: Optional Roof-Area and Premium Data Enhancements

Build:

- Optional Google Solar API connector
- Optional paid data provider connectors
- Roof area vs footprint comparison
- Discrepancy warning
- Commercial roof measurement report enhancements

Success criteria:

- Solar or premium data can supplement footprint area.
- Roof area and footprint area are clearly distinguished.
- Reports show source-specific warnings.

## Phase 6: Estimating Integration

Build:

- Material quantity estimates
- Waste factors
- Coating rate inputs
- Perimeter detail estimates
- Multi-section roof area aggregation
- Report export
- CRM/estimator handoff

Success criteria:

- Measurement can become a preliminary estimating input.
- Estimate clearly states assumptions.
- Field verification remains required.

---

# Recommended Tech Stack

## Backend

Recommended:

- Python FastAPI or Node/TypeScript API
- PostGIS
- Redis for job queue/cache
- Object storage for artifacts and imagery metadata
- Background workers for large geospatial imports

Python geospatial stack:

- Shapely
- GeoPandas
- PyProj
- Rasterio
- Fiona
- rio-tiler
- FastAPI
- SQLAlchemy or SQLModel

TypeScript geospatial stack:

- Turf.js
- proj4
- MapLibre
- OpenLayers
- Prisma or Drizzle
- Node Postgres client

Database:

- PostgreSQL + PostGIS

## Frontend

Recommended:

- React
- MapLibre GL JS or OpenLayers
- Turf.js
- Drawing/editing library
- Zustand or Redux for map state
- TanStack Query for API state

## AI

Recommended:

- Local vision model or API vision model for permitted imagery
- Structured JSON outputs
- Separate AI reviewer from geometry engine
- Confidence and warning schema

## Deployment

MVP:

- Single server
- PostGIS database
- Local building footprint index
- Map client

Production:

- Background import pipeline
- Data-source monitoring
- API key management
- Usage logging
- Provider cost tracking
- Legal/licensing flags by source

---

# Security and Compliance

## API Key Handling

- Store keys in environment variables or secrets manager.
- Restrict API keys by domain/IP where possible.
- Separate development and production keys.
- Log usage by provider.
- Do not expose secret keys to browser.

## Data Licensing Tracking

Every source should have metadata:

```ts
type SourceLicense = {
  sourceName: string;
  licenseName: string;
  attributionRequired: boolean;
  commercialUseAllowed: boolean;
  cachingAllowed: boolean;
  derivativeDataAllowed: boolean;
  aiProcessingAllowed: boolean;
  reportImageAllowed: boolean;
  notes: string;
  verifiedAt: string;
};
```

## Hard Rule

Do not process imagery with AI unless `aiProcessingAllowed` is true or the user has supplied/approved imagery with sufficient rights.

---

# Testing Plan

## Unit Tests

- Area calculation
- Perimeter calculation
- Projection handling
- Polygon validation
- Multipolygon handling
- Candidate ranking
- Confidence scoring
- Unit conversion

## Integration Tests

- Geocode to footprint
- Microsoft lookup
- OSM lookup
- County GIS lookup
- Manual edit save
- Report export
- AI review with mock imagery

## Regression Tests

Use fixed addresses with known expected behavior:

- Single building on parcel
- Multiple buildings on parcel
- No footprint available
- Bad geocoder result
- Large commercial building
- Courtyard building
- Pitched residential roof
- Tree-obscured building
- Newly built structure missing from dataset

## Accuracy Checks

For a validation set:

- Compare against known survey/roof report
- Compare source footprint vs manual outline
- Compare footprint area vs Solar API roof area where available
- Track percent error
- Track false candidate selections
- Track user correction frequency

---

# Product Language

## Preferred User-Facing Labels

- Preliminary footprint area
- Estimated roof area
- Source
- Confidence
- Needs verification
- User verified
- AI visual check
- Manual correction
- Export report

## Avoid

- Guaranteed area
- Final roof takeoff
- Exact measurement
- Google Earth extraction
- AI measured this roof
- Certified roof area

## Good User Message Example

```text
Estimated footprint: 42,380 sq ft.
Confidence: Medium.
Source: Microsoft building footprint, visually checked against public aerial imagery.
Warning: Possible canopy or addition on the north side. Manual verification recommended before estimating materials.
```

---

# Final Recommendation

Build the system around this priority order:

1. Existing building polygons
2. Geometry-based area calculation
3. Public or licensed imagery for verification
4. Manual correction
5. AI visual review
6. Optional roof-area APIs
7. Paid data enhancements
8. Estimating integration

This keeps the product efficient, useful, and less legally problematic.

AI should make the estimator faster and smarter, but geometry should hold the tape measure.
