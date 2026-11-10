# MASTER PROMPT: CLIMADA-Based Multi-Hazard Landslide Risk, Damage and Loss Assessment Module

## ROLE AND OBJECTIVE

Act as a senior geospatial software architect, computational landslide modeller, disaster risk scientist, infrastructure vulnerability specialist, and Python developer with expertise in:

- CLIMADA Core and CLIMADA Petals
- Probabilistic disaster risk assessment
- Landslide and rockfall impact modelling
- Debris-flow mechanics and physical vulnerability
- Remote sensing, GIS and spatial data processing
- Economic loss and infrastructure damage modelling
- Climate risk and adaptation assessment
- Python-based geospatial application development

Your task is to design a **complete, scientifically defensible, technically detailed and implementation-ready Risk, Damage and Loss Assessment Module** that can be integrated into my existing landslide simulation platform using CLIMADA Core and relevant CLIMADA Petals functionality.

The final system must convert simulated landslide and rockfall hazards into spatially explicit physical impacts, direct economic losses, infrastructure disruptions, probabilistic risk indicators and adaptation decision-support outputs.

**Do not redesign, replace or simplify my existing landslide simulation engine. Build the new risk module around it.**

I will provide the existing project methodology, technical reference documentation, available datasets and, where available, the existing source-code structure.

Read these materials before proposing the integration.

---

# PART 1 — UNDERSTAND THE EXISTING LANDSLIDE PLATFORM

My existing platform is designed for Pakistan, with Gilgit and surrounding mountainous areas as an initial implementation area.

It includes or is intended to include the following modelling components:

1. CNN–DNN landslide susceptibility modelling.
2. Rainfall-triggered slope instability.
3. Green–Ampt soil infiltration.
4. Time-dependent infinite-slope Factor of Safety.
5. Landslide initiation and failure-time estimation.
6. Earthquake-triggered instability using PGA and Newmark displacement.
7. Voellmy-based landslide/debris runout simulation.
8. Rockfall movement and impact simulation.
9. Terrain, soil, geology, rainfall and seismic inputs.
10. Historical landslide inventory integration.
11. Multi-event and scenario-based simulations.
12. GIS-based outputs and dashboard visualization.

Treat these as existing or proposed capabilities, not as verified implementations. Inspect the supplied methodology and code to determine which components actually exist and which are incomplete.

Identify the outputs that can be obtained from each physical modelling component, particularly:

- Landslide initiation locations
- Failure probabilities, where available
- Factor of Safety
- Failure timing
- Runout footprints
- Debris depth or thickness
- Flow velocity
- Impact pressure or other physically justified intensity measures
- Deposited material volumes
- Rockfall trajectories
- Rockfall energy and impact locations
- Hazard extent and exposure duration
- Event and scenario identifiers

Distinguish actual model outputs from quantities that would require additional equations, calculations, datasets or model development.

Do not invent available data or assume that every variable exists.

### Required analysis

Examine the existing architecture and explain:

- Which modules should remain unchanged.
- Which outputs can directly enter CLIMADA.
- Which outputs require conversion or preprocessing.
- Which missing outputs are necessary for physically meaningful loss estimation.
- Which integration steps can be achieved without rerunning the existing simulation.
- Which additions require modifications to the existing simulation output interface.
- Which outputs cannot be used directly for credible economic loss modelling.

Preserve the existing study-area boundary, modelling methodology and configured datasets unless a specific technical issue requires correction.

---

# PART 2 — VERIFY CLIMADA CORE AND PETALS CAPABILITIES

Conduct a technical review of the current official CLIMADA Core and CLIMADA Petals documentation, examples, source code and supported APIs.

Official starting points:

CLIMADA Core:
https://github.com/CLIMADA-project/climada_python

CLIMADA Petals:
https://github.com/CLIMADA-project/climada_petals

Core documentation:
https://climada-python.readthedocs.io/

Petals documentation:
https://climada-petals.readthedocs.io/

Investigate relevant classes and functionality, including:

- `Hazard`
- `Exposures`
- `ImpactFunc`
- `ImpactFuncSet`
- `ImpactCalc`
- `Impact`
- Landslide classes available in CLIMADA Petals
- `Landslide.from_hist()`
- `Landslide.from_prob()`
- Uncertainty analysis
- Impact exceedance and risk calculations
- Adaptation and cost-benefit functions
- Specialized exposure or infrastructure tools where applicable

Verify exact imports, signatures, supported hazard types, data formats and package compatibility against the currently available software version.

Do not assume APIs from older examples remain unchanged.

### Required comparison

Produce a technical comparison between:

1. The capabilities of my existing landslide platform.
2. CLIMADA Core.
3. CLIMADA Petals.
4. Additional custom functionality that would be necessary.

For each proposed function, explicitly state whether it is:

- Natively supported by CLIMADA Core.
- Natively supported by CLIMADA Petals.
- Supported through configurable CLIMADA functionality.
- Possible only through a custom Python implementation.
- Not currently feasible with the available data.

Clearly distinguish CLIMADA's probabilistic hazard and impact capabilities from physical landslide propagation and simulation.

Do not claim that CLIMADA Petals improves physical landslide predictions unless there is documented evidence.

---

# PART 3 — DEFINE THE COMPLETE RISK AND LOSS ASSESSMENT FRAMEWORK

Design a modular system covering the following components.

## Module A — Hazard Output Integration

Create a data-processing interface between the existing landslide simulation platform and CLIMADA.

The interface must support:

- Historical landslide events.
- Rainfall-triggered landslide scenarios.
- Earthquake-triggered landslide scenarios.
- Debris-flow runout outputs.
- Rockfall simulation outputs.
- Future rainfall or climate scenarios, where scientifically appropriate.
- Multiple events and scenario comparisons.

Define procedures for converting the simulation results into CLIMADA-compatible hazard data.

Include:

- Coordinate reference system handling.
- Raster/vector conversions.
- Spatial resolution consistency.
- Hazard centroid generation.
- Event identifiers.
- Event dates.
- Hazard intensity representation.
- Hazard frequency handling.
- NoData masking.
- Sparse matrix storage.
- Event metadata.
- Input and output validation.

Do not assign arbitrary annual occurrence probabilities to deterministic scenarios.

Explain how to handle multiple hazard intensities such as debris depth, velocity, pressure and rockfall kinetic energy without incorrectly combining quantities that have different physical meanings.

Recommend a suitable strategy for custom hazard classes, separate hazard objects or preprocessing when the default CLIMADA model cannot directly represent multivariate hazard intensity.

## Module B — Exposure and Asset Intelligence

Develop an asset-exposure assessment system covering:

**Buildings**
- Residential buildings
- Commercial buildings
- Schools
- Hospitals
- Government buildings
- Industrial buildings

**Transport**
- Roads
- Bridges
- Road intersections
- Critical access routes

**Utilities**
- Electricity infrastructure
- Water supply networks
- Telecommunications
- Fuel infrastructure

**Agriculture**
- Agricultural parcels
- Crop areas
- Irrigation systems

**Population**
- Residential population
- Exposed settlements
- Vulnerable groups, where reliable and appropriately aggregated data are available

For each asset category, identify:

1. Required spatial datasets.
2. Essential attributes.
3. Recommended free data sources.
4. Possible local government or field-survey sources.
5. Asset replacement-cost estimation methods.
6. Exposure calculation techniques.
7. Data-quality requirements.
8. Uncertainty and limitations.

Prioritize datasets already present on the computer.

Before downloading any new dataset, inspect the existing configured data paths, file coverage, CRS, spatial resolution, date, validity and attribute completeness.

Download only genuinely missing inputs.

Avoid repeated datasets serving the same purpose.

Differentiate replacement value, market value, repair cost and economic activity value.

Prevent double-counting where multiple datasets describe the same asset.

## Module C — Physical Damage and Vulnerability

Develop vulnerability functions for the relevant landslide and rockfall processes.

Consider:

- Shallow landslides
- Deep-seated landslides
- Debris flows
- Rockfalls
- Earthquake-triggered slope failures

Define scientifically appropriate intensity–damage relationships for:

- Buildings
- Roads
- Bridges
- Electricity infrastructure
- Water supply systems
- Agricultural land
- Other critical assets

Assess whether damage estimation should use:

- Debris depth
- Flow velocity
- Dynamic pressure
- Impact energy
- Deposited volume
- Footprint overlap
- Burial depth
- Structural material
- Building type
- Foundation characteristics
- Asset condition

Identify documented vulnerability and fragility relationships from peer-reviewed research.

Explain which relationships are transferable to Gilgit/Pakistan and which require local calibration.

Where reliable empirical vulnerability relationships are unavailable, propose transparent scenario-based assumptions rather than inventing calibrated functions.

Distinguish:

- Hazard intensity
- Probability of damage
- Degree of physical damage
- Proportion of an asset affected
- Mean damage ratio
- Financial loss

Explain how CLIMADA `ImpactFunc` can be configured for relevant hazards and asset types.

For multivariate damage models, specify whether calculations should be completed outside CLIMADA before importing derived damage ratios.

Do not automatically treat footprint intersection as total asset destruction.

## Module D — Direct Economic Loss Assessment

Calculate asset-level and event-level economic damage.

Include:

- Building repair and replacement costs
- Road rehabilitation costs
- Bridge repair or replacement costs
- Utility equipment losses
- Agricultural crop losses
- Land rehabilitation costs
- Infrastructure restoration costs

Use the general formulation:

**Direct Loss = Exposed Asset Value × Mean Damage Ratio**

Where a different cost method is more appropriate, explain and implement it separately.

Outputs must include:

- Loss per asset
- Loss per asset class
- Loss per event
- Loss per settlement
- Loss per administrative area
- Loss per simulated scenario
- Total direct economic loss

Prefer PKR as the reporting currency and preserve original valuation assumptions.

Specify price year, currency conversion basis where required, inflation adjustments and unit-cost sources.

Do not mix monetary estimates from different years without adjustment.

## Module E — Indirect and Cascading Losses

Assess the feasibility of estimating:

- Road closures
- Travel delays
- Community isolation
- Disrupted access to hospitals
- School access disruption
- Electricity outages
- Water-supply interruptions
- Business interruption
- Supply-chain disruption
- Agricultural market access disruption

Identify which impacts require:

- Network analysis
- Dependency graphs
- Traffic demand data
- Service-area modelling
- Restoration-time assumptions
- Additional economic models

Use CLIMADA Petals infrastructure functionality where genuinely applicable.

Do not represent indirect economic losses as automatically calculated by the standard CLIMADA impact engine.

Avoid double-counting direct damage, repair expenditures and business interruption.

Distinguish immediate infrastructure damage from resulting service interruption.

## Module F — Population Exposure and Human Impacts

Estimate:

- Population inside the simulated hazard area.
- Population potentially affected by blocked transport routes.
- Settlements with disrupted access.
- Critical facilities exposed.
- Population exposure under different event scenarios.

For mortality or injury estimation, require an appropriate validated casualty or vulnerability model.

Do not infer fatalities directly from the number of people inside a landslide footprint.

Clearly separate exposed population, affected population, displaced population, injuries and fatalities.

## Module G — Probabilistic Risk Assessment

Design an event-based risk analysis system that supports:

- Multiple simulated landslide events.
- Historical-event impact analysis.
- Annual occurrence models.
- Event frequency assignment.
- Expected annual damage.
- Expected annual loss.
- Event loss exceedance curves.
- Annual aggregate loss exceedance curves, when event modelling supports them.
- Return-period loss estimates.
- Risk distribution across assets and settlements.

Explain when Petals `Landslide.from_hist()` and `Landslide.from_prob()` are useful.

Clarify whether their event generation and hazard representations are appropriate for local-scale Gilgit landslide modelling.

Determine how occurrence probabilities, conditional event intensities, simulated years and event frequencies should be represented.

Avoid using susceptibility probabilities as annual occurrence probabilities without a defensible temporal calibration.

Avoid assigning equal annual frequency to every simulated scenario.

Explain the limitations of incomplete historical inventories and biased event reporting.

Where occurrence probabilities cannot be calibrated, provide scenario-specific loss estimates instead of unsupported expected annual loss figures.

## Module H — Climate Change and Future Risk

Evaluate how future precipitation, temperature, snowmelt and relevant climatic drivers could affect landslide risk.

Explain how climate scenarios can enter the existing physical landslide model rather than being inserted directly into the loss calculation without physical justification.

Assess:

- Future hazard frequency
- Future hazard intensity
- Changing land use
- Future settlement expansion
- Changing asset values
- Infrastructure development
- Exposure growth

Clearly distinguish hazard change, exposure change and vulnerability change.

Avoid presenting long-term landslide risk projections as deterministic forecasts.

## Module I — Risk Reduction and Adaptation Assessment

Develop decision-support calculations for:

- Slope stabilization
- Retaining structures
- Rockfall protection barriers
- Debris-flow retention structures
- Drainage improvements
- Early warning systems
- Road protection works
- Settlement-level mitigation
- Land-use restrictions
- Infrastructure reinforcement

Calculate, where supported by data:

- Baseline risk
- Post-intervention risk
- Avoided damage
- Investment costs
- Maintenance costs
- Benefit-cost ratio
- Net present value
- Payback assumptions
- Intervention performance uncertainty

Explain that engineering interventions require credible assumptions about how they change hazard intensity, probability or vulnerability.

Do not apply arbitrary percentage reductions to economic loss without justification.

---

# PART 4 — SCIENTIFIC METHODS AND EQUATIONS

For every proposed calculation, provide:

1. Physical or mathematical concept.
2. Complete equation.
3. Definition of every variable.
4. Units.
5. Required input datasets.
6. Data preprocessing.
7. Assumptions.
8. Implementation method.
9. Expected outputs.
10. Limitations.
11. Validation approach.
12. Scientific or official documentation reference.

Include equations for:

- Hazard intensity at each asset.
- Spatial exposure intersection.
- Mean damage ratio.
- Asset-level direct loss.
- Event-level total loss.
- Expected annual loss.
- Loss exceedance probability.
- Damage uncertainty.
- Risk reduction.
- Avoided expected damage.
- Cost-benefit ratio.
- Net present value.

Explain how asset polygons and linear infrastructure should be processed so that the calculations do not incorrectly assign full-asset value to every intersecting raster cell.

Identify suitable approaches for partial overlap, segmented road assets and asset aggregation.

---

# PART 5 — DATA REQUIREMENTS AND FREE DATA SOURCES

Produce a complete dataset inventory table containing:

| Dataset | Purpose | Parameters | Source | Resolution | Format | Free? | Existing/New | Priority |
|---|---|---|---|---|---|---|---|---|

Prioritize:

- Existing local model outputs.
- OpenStreetMap building and infrastructure layers.
- Official administrative boundaries.
- Available population datasets.
- NASA landslide inventory.
- Existing geology and terrain data.
- Relevant peer-reviewed damage functions.
- Available government cost information.

Use only datasets necessary for the selected functions.

Do not recommend downloading complete global datasets when they can be spatially filtered, clipped or obtained for the study area.

Do not assume an open dataset provides building replacement costs or structural characteristics unless these attributes actually exist.

Identify missing inputs that cannot reliably be obtained from free satellite or GIS datasets.

Provide realistic fallback methods and document the resulting uncertainty.

---

# PART 6 — SOFTWARE ARCHITECTURE AND INTEGRATION DESIGN

Design a modular Python architecture compatible with my existing platform.

Propose a directory structure similar to:

```text
landslide_platform/
    existing_hazard_engine/
    risk_assessment/
        config/
        adapters/
        hazard/
        exposure/
        vulnerability/
        direct_loss/
        indirect_loss/
        population/
        probabilistic_risk/
        climate_scenarios/
        adaptation/
        validation/
        reporting/
        api/
        tests/
```

Modify this structure if the existing repository uses a different architecture.

Define:

- Responsibilities of each module.
- Core Python classes.
- Required functions.
- Data schemas.
- File formats.
- API endpoints.
- Event identifiers.
- Intermediate outputs.
- Final outputs.
- Error-handling procedures.
- Logging.
- Configuration management.
- Data caching.
- Dependency management.
- Validation checks.

Prefer a clean interface between the existing simulation engine and the new risk assessment module.

Include:

1. A `SimulationOutputAdapter`.
2. A `CLIMADAHazardAdapter`.
3. An `ExposureBuilder`.
4. A `VulnerabilityManager`.
5. An `AssetLossCalculator`.
6. A `ProbabilisticRiskEngine`.
7. An `InfrastructureImpactAnalyzer`.
8. An `AdaptationAnalyzer`.
9. A `RiskReportGenerator`.

Class names may be modified based on the actual codebase.

Explain which parts should directly use CLIMADA APIs and which need custom code.

Do not introduce unnecessary software frameworks or services.

---

# PART 7 — WORKING IMPLEMENTATION EXAMPLES

Provide technically valid Python examples for:

1. Reading existing landslide simulation outputs.
2. Validating raster metadata and units.
3. Converting runout rasters into CLIMADA hazard objects.
4. Importing building and infrastructure exposure.
5. Assigning asset values.
6. Building appropriate CLIMADA impact functions.
7. Running an event-level impact calculation.
8. Exporting asset-level damage results.
9. Generating spatial loss maps.
10. Calculating expected annual losses where event probabilities are available.
11. Producing loss exceedance curves.
12. Comparing baseline and intervention scenarios.
13. Exporting results to the existing application dashboard.

Verify code against the installed or explicitly selected CLIMADA version.

Do not write pseudocode and present it as executable software.

Clearly label examples requiring user-specific file paths, local datasets or unavailable vulnerability coefficients.

Provide unit tests and a small synthetic example that can run without downloading large external datasets.

---

# PART 8 — DASHBOARD AND GIS OUTPUTS

Design the functionality of the new risk and loss assessment dashboard module.

Do not redesign the entire existing dashboard.

The new module should include:

### Risk overview

- Selected hazard event
- Event/scenario type
- Number of affected assets
- Total direct economic loss
- Exposed population
- Affected infrastructure
- Model confidence or uncertainty information

### Spatial damage assessment

Display:

- Landslide runout extent
- Rockfall impact locations
- Buildings classified by estimated damage
- Damaged road segments
- Exposed bridges
- Critical infrastructure
- Asset-level financial loss
- Loss density or aggregated loss maps

### Scenario comparison

Allow comparisons between:

- Rainfall-triggered events
- Earthquake-triggered events
- Different storm intensities
- Multiple landslide events
- Baseline and future scenarios
- Mitigated and unmitigated scenarios

### Financial risk analysis

Display:

- Direct loss by asset class
- Loss by settlement
- Loss by administrative area
- Expected annual loss, if statistically supportable
- Loss exceedance curves
- Uncertainty ranges
- High-risk asset rankings

### Adaptation assessment

Display:

- Proposed mitigation intervention
- Baseline loss
- Estimated post-intervention loss
- Avoided loss
- Estimated investment cost
- Benefit-cost ratio, if supportable
- Sensitivity analysis

Keep computational modelling separate from frontend rendering.

Ensure that GIS data and risk results can be exported as GeoPackage, GeoTIFF, CSV, JSON and appropriate summary reports.

Specify how each dashboard output is linked back to its input datasets, scenario settings and model assumptions.

---

# PART 9 — VALIDATION, CALIBRATION AND UNCERTAINTY

Develop a detailed validation methodology.

Separate the assessment of:

**1. Hazard model validity**
- Landslide occurrence prediction
- Hazard footprint accuracy
- Runout distance accuracy
- Hazard intensity accuracy

**2. Exposure-data validity**
- Building inventory completeness
- Road and bridge completeness
- Asset location accuracy
- Asset classification accuracy
- Asset valuation uncertainty

**3. Vulnerability-model validity**
- Damage ratio validation
- Structural type relevance
- Intensity–damage relationship validity
- Transferability from published studies

**4. Financial-loss validity**
- Predicted versus observed damage cost
- Bias
- Mean absolute error
- Root mean squared error
- Relative error where appropriate
- Calibration and independent validation

**5. Probabilistic-risk validity**
- Historical occurrence consistency
- Event-frequency uncertainty
- Sampling convergence
- Loss exceedance sensitivity
- Inventory reporting bias

Explain how to distinguish model calibration data from independent validation data.

Provide methods for conducting sensitivity analysis and uncertainty propagation.

Identify which assumptions dominate economic loss uncertainty.

Recommend methods for producing credible uncertainty intervals rather than simply attaching arbitrary confidence percentages.

---

# PART 10 — COMPUTATIONAL PERFORMANCE

The implementation must support CPU execution.

Avoid unnecessary GPU dependencies.

Optimize for:

- Limited RAM
- Raster-based GIS operations
- Large road networks
- Thousands of buildings
- Multiple landslide scenarios
- Sparse hazard matrices
- Caching of unchanged exposure data
- Reuse of previously simulated events
- Incremental processing
- Batch processing
- Spatial indexing
- Efficient geospatial intersections

Do not rerun physical landslide simulations when risk assessment can operate on existing outputs.

Estimate computational memory and processing requirements for a small Gilgit pilot, clearly stating hardware and data-size assumptions.

Do not invent benchmark performance.

---

# PART 11 — IMPLEMENTATION PRIORITIES

Divide the development into practical phases.

**Phase 1 — Minimum Viable Impact Assessment**

- Existing hazard output import
- Buildings and roads exposure
- Basic vulnerability functions
- Single-event direct damage estimation
- Asset-level loss maps
- CSV and GeoPackage exports

**Phase 2 — Advanced Asset Risk**

- Bridges
- Utilities
- Agriculture
- Detailed vulnerability functions
- Population exposure
- Observed-loss validation
- Damage uncertainty

**Phase 3 — Probabilistic Risk**

- Historical hazard analysis
- CLIMADA Petals integration
- Event occurrence modelling
- Expected annual loss
- Exceedance curves
- Multi-event analysis

**Phase 4 — Infrastructure Disruption**

- Road network connectivity
- Community isolation
- Travel disruption
- Critical service interruption
- Indirect economic effects

**Phase 5 — Climate Adaptation and Decision Support**

- Future risk scenarios
- Mitigation scenario analysis
- Avoided damage
- Cost-benefit analysis
- Intervention prioritization

For each phase, provide:

- Objectives
- Exact CLIMADA features
- Required datasets
- Required Python modules
- Implementation tasks
- Dependencies
- Expected outputs
- Validation criteria
- Computational requirements
- Completion criteria

Identify tasks that can run independently or in parallel.

---

# PART 12 — IMPORTANT DEVELOPMENT CONSTRAINTS

Follow these rules throughout the methodology:

1. Preserve the existing landslide physical simulation methodology.
2. Do not replace the current susceptibility, infiltration, slope-stability or runout solvers with CLIMADA.
3. Use CLIMADA primarily for hazard-to-impact conversion, loss modelling and risk assessment.
4. Use Petals only where its specialized capabilities provide a demonstrable advantage.
5. Prefer free and open-source datasets and software.
6. Reuse existing locally available datasets.
7. Avoid unnecessary downloads.
8. Do not introduce duplicate datasets for identical purposes.
9. Keep the existing study area unchanged.
10. Support CPU processing.
11. Do not require Google Earth Engine authentication.
12. Avoid paid APIs unless explicitly marked as optional.
13. Do not invent damage curves or economic coefficients.
14. Do not invent historical validation results.
15. Do not treat susceptibility scores as calibrated annual failure probabilities.
16. Distinguish physical simulation, event-impact assessment and probabilistic risk.
17. Preserve all event, scenario and data provenance.
18. Provide explicit units and currency assumptions.
19. Avoid double-counting asset and economic losses.
20. Keep advanced technical parameters configurable, with reasonable user-facing defaults only where scientifically justified.
21. Do not assume the existing codebase implements a feature simply because the methodology mentions it.
22. Do not generate a large amount of unnecessary code before confirming the required integration architecture.

---

# PART 13 — REQUIRED FINAL DELIVERABLES

Produce the following deliverables in order.

### Deliverable 1 — Existing Platform Assessment

A detailed technical audit of the existing model, available output variables, missing components and compatibility with CLIMADA.

### Deliverable 2 — CLIMADA Core vs Petals Assessment

A verified feature comparison explaining exactly which CLIMADA components should be integrated and why.

### Deliverable 3 — Complete Technical Methodology

A comprehensive methodology for all proposed risk, damage and economic-loss functions, including physical concepts, equations, inputs, assumptions and expected outputs.

### Deliverable 4 — Dataset Requirements

A structured dataset inventory, identifying existing datasets, genuinely missing data and practical acquisition methods.

### Deliverable 5 — Integration Architecture

A software architecture diagram, module interaction diagram, file structure, API specifications and event-data schemas.

### Deliverable 6 — Implementation Blueprint

Detailed Python implementation instructions, verified CLIMADA APIs, processing logic, configuration and integration points.

### Deliverable 7 — Validation and Calibration Framework

A complete protocol for validating physical damage estimates, financial losses, historical event predictions and probabilistic results.

### Deliverable 8 — Dashboard Functional Specification

An exact specification for adding risk and loss assessment capabilities to the existing dashboard without changing unrelated functionality.

### Deliverable 9 — Phased Development Roadmap

An implementation sequence prioritizing high-value, low-complexity functions first, followed by advanced risk assessment.

### Deliverable 10 — Technical Risk and Limitation Register

Identify:

- Missing data
- Scientific uncertainties
- Unsupported functionality
- Model limitations
- API and package compatibility risks
- Potential double-counting
- Scale and resolution limitations
- Computational constraints
- Validation requirements

For every risk, recommend a feasible mitigation or fallback.

---

# FINAL INSTRUCTIONS

I do not want a generic description of landslide risk assessment.

I want a **project-specific, implementation-ready technical methodology** showing precisely how to integrate CLIMADA Core and CLIMADA Petals into my existing landslide platform.

Use the supplied methodology and actual repository structure as the primary technical references.

For each proposed capability, explain:

1. Why it is required.
2. What physical or economic concept it represents.
3. What input data it needs.
4. Whether the existing platform already supplies those inputs.
5. Whether CLIMADA Core, Petals or custom Python implements it.
6. Which equations and processing steps it uses.
7. What outputs it produces.
8. How those outputs are validated.
9. How the function integrates into the existing dashboard.
10. Whether it materially improves accuracy, functionality, interpretability or decision-making.

Clearly distinguish **improved accuracy** from **additional functionality**.

Do not claim that a function improves results without identifying a plausible mechanism and validation method.

Where data or implementation information is missing, explicitly identify the gap and propose a defensible fallback.

Use clear technical tables, equations, architecture diagrams and numbered implementation procedures.

Cite official CLIMADA documentation and scientific publications for specialized methods.

Prioritize feasible integration over unnecessary model complexity.

**First produce the detailed methodology and architecture, not the complete application source code.** The implementation should begin only after the methodology, integration interfaces, data dependencies and validation strategy have been established.

Start by auditing the supplied existing landslide platform documentation, then proceed through the required deliverables in order.