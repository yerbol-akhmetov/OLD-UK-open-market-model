# -*- coding: utf-8 -*-
"""
Script to create region shapes by dividing country shapes based on boundary lines.

This script reads country shapes from a GeoJSON file and divides them using
boundary lines from the ETYS boundary data to create regional divisions.
The resulting regions are saved as a new GeoJSON file.
"""

import logging
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import split
from shapely.geometry import Point

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_country_shapes(filepath):
    """
    Load country shapes from GeoJSON file.

    Args:
        filepath (str): Path to the country shapes GeoJSON file

    Returns:
        geopandas.GeoDataFrame: Country shapes data
    """
    try:
        logger.info(f"Loading country shapes from: {filepath}")
        country_gdf = gpd.read_file(filepath)
        logger.info(f"Loaded {len(country_gdf)} country shapes")
        return country_gdf
    except Exception as e:
        logger.error(f"Error loading country shapes: {e}")
        raise


def load_boundary_lines(filepath):
    """
    Load boundary lines from shapefile or GeoJSON.

    Args:
        filepath (str): Path to the boundary lines file

    Returns:
        geopandas.GeoDataFrame: Boundary lines data
    """
    try:
        logger.info(f"Loading boundary lines from: {filepath}")
        boundary_gdf = gpd.read_file(filepath)
        logger.info(f"Loaded {len(boundary_gdf)} boundary features")
        return boundary_gdf
    except Exception as e:
        logger.error(f"Error loading boundary lines: {e}")
        raise


def ensure_same_crs(gdf1, gdf2):
    """
    Ensure both GeoDataFrames have the same CRS.

    Args:
        gdf1, gdf2 (geopandas.GeoDataFrame): GeoDataFrames to align

    Returns:
        tuple: Both GeoDataFrames with the same CRS
    """
    if gdf1.crs != gdf2.crs:
        logger.info(f"Converting CRS from {gdf2.crs} to {gdf1.crs}")
        gdf2 = gdf2.to_crs(gdf1.crs)
    return gdf1, gdf2


def create_regions_from_boundaries(country_shapes, boundary_lines):
    """
    Create regions by dividing country shapes using boundary lines.

    Args:
        country_shapes (geopandas.GeoDataFrame): Country polygons
        boundary_lines (geopandas.GeoDataFrame): Boundary lines for division

    Returns:
        geopandas.GeoDataFrame: Regional divisions
    """
    logger.info("Creating regions from boundaries...")

    # Convert to a projected CRS for accurate area calculations
    # Use British National Grid (EPSG:27700) which is appropriate for UK
    target_crs = "EPSG:27700"
    logger.info(f"Converting to projected CRS {target_crs} for accurate measurements")

    if country_shapes.crs != target_crs:
        country_shapes = country_shapes.to_crs(target_crs)
        logger.info(
            f"Country shapes converted. New total area: {country_shapes.geometry.area.sum() / 1000000:.0f} km²"
        )
    if boundary_lines.crs != target_crs:
        boundary_lines = boundary_lines.to_crs(target_crs)
        logger.info(
            f"Boundary lines converted. Length range: {boundary_lines.geometry.length.min():.0f} - {boundary_lines.geometry.length.max():.0f} meters"
        )

    # Validate and clean boundary lines first
    boundary_lines = validate_and_fix_boundary_data(boundary_lines)

    if len(boundary_lines) == 0:
        logger.warning("No valid boundary lines found!")
        return country_shapes.copy()

    logger.info(f"Using {len(boundary_lines)} boundary lines for splitting")

    regions = []
    region_id = 1

    for idx, country in country_shapes.iterrows():
        logger.info(f"Processing country/region {idx + 1}/{len(country_shapes)}")

        try:
            # Start with the original country geometry
            current_polygons = [country.geometry]
            split_count = 0

            # Process each boundary line
            for boundary_idx, boundary in boundary_lines.iterrows():
                boundary_geom = boundary.geometry
                new_polygons = []

                for polygon in current_polygons:
                    # Check if boundary intersects this polygon
                    if polygon.intersects(boundary_geom):
                        try:
                            # Attempt to split the polygon
                            split_result = split(polygon, boundary_geom)

                            # Check if splitting actually occurred
                            if hasattr(split_result, "geoms"):
                                split_geoms = list(split_result.geoms)
                                logger.info(
                                    f"Split produced {len(split_geoms)} geometries"
                                )
                                if len(split_geoms) > 1:
                                    # Successfully split - add all valid pieces
                                    valid_pieces = 0
                                    for geom in split_geoms:
                                        if (
                                            geom.is_valid
                                            and not geom.is_empty
                                            and geom.geom_type
                                            in ["Polygon", "MultiPolygon"]
                                            and geom.area > 1000000
                                        ):  # 1 km² minimum (1,000,000 sq meters in projected CRS)
                                            new_polygons.append(geom)
                                            valid_pieces += 1
                                        else:
                                            logger.debug(
                                                f"Filtered out small geometry: area={geom.area:.0f} sq meters"
                                            )

                                    if valid_pieces > 0:
                                        split_count += 1
                                        logger.info(
                                            f"Split polygon into {valid_pieces} valid pieces (from {len(split_geoms)} total)"
                                        )
                                    else:
                                        logger.warning(
                                            f"All {len(split_geoms)} split pieces were too small - keeping original"
                                        )
                                        new_polygons.append(polygon)
                                else:
                                    # No actual split occurred
                                    new_polygons.append(polygon)
                            else:
                                # Single geometry result - no split
                                new_polygons.append(polygon)

                        except Exception as split_error:
                            logger.warning(
                                f"Split failed for boundary {boundary_idx}: {split_error}"
                            )
                            new_polygons.append(polygon)
                    else:
                        # No intersection - keep original polygon
                        new_polygons.append(polygon)

                # Update current polygons for next iteration
                current_polygons = new_polygons

            logger.info(
                f"Country {idx} split into {len(current_polygons)} regions using {split_count} boundaries"
            )

            # Create region entries from final polygons
            for i, polygon in enumerate(current_polygons):
                if polygon.is_valid and not polygon.is_empty:
                    # Create region data
                    region_data = country.copy()
                    region_data["geometry"] = polygon
                    region_data["region_id"] = f"region_{region_id:03d}"
                    region_data["original_country_id"] = idx
                    region_data["sub_region_id"] = i
                    region_data["area_km2"] = polygon.area / 1000000  # Convert to km²
                    region_data["num_boundaries_used"] = split_count

                    regions.append(region_data)
                    region_id += 1

        except Exception as e:
            logger.error(f"Error processing country {idx}: {e}")
            # Fallback: keep original geometry
            region_data = country.copy()
            region_data["region_id"] = f"region_{region_id:03d}"
            region_data["original_country_id"] = idx
            region_data["sub_region_id"] = 0
            region_data["area_km2"] = country.geometry.area / 1000000
            region_data["num_boundaries_used"] = 0
            regions.append(region_data)
            region_id += 1

    # Create GeoDataFrame from regions
    if regions:
        regions_gdf = gpd.GeoDataFrame(regions, crs=country_shapes.crs)
        logger.info(
            f"Successfully created {len(regions_gdf)} regions from {len(country_shapes)} original shapes"
        )
        return regions_gdf
    else:
        logger.error("No regions were created!")
        return country_shapes.copy()


def validate_and_fix_boundary_data(boundary_lines):
    """
    Validate and fix boundary line data.

    Args:
        boundary_lines (geopandas.GeoDataFrame): Raw boundary lines

    Returns:
        geopandas.GeoDataFrame: Cleaned boundary lines
    """
    logger.info("Validating and fixing boundary data...")

    valid_boundaries = []
    fixed_count = 0

    for idx, row in boundary_lines.iterrows():
        try:
            geom = row.geometry

            # Skip if geometry is None or empty
            if geom is None or geom.is_empty:
                continue

            # Handle different geometry types
            if geom.geom_type == "LineString":
                # Check if coordinates are valid
                coords = list(geom.coords)
                if len(coords) >= 2:
                    # Validate coordinate structure
                    valid_coords = []
                    for coord in coords:
                        if len(coord) >= 2 and all(
                            isinstance(x, (int, float)) for x in coord[:2]
                        ):
                            valid_coords.append(coord[:2])  # Take only x, y

                    if len(valid_coords) >= 2:
                        # Create new valid LineString
                        from shapely.geometry import LineString

                        new_geom = LineString(valid_coords)
                        if new_geom.is_valid and not new_geom.is_empty:
                            row_copy = row.copy()
                            row_copy["geometry"] = new_geom
                            valid_boundaries.append(row_copy)
                            if new_geom != geom:
                                fixed_count += 1

            elif geom.geom_type == "MultiLineString":
                # Process each LineString component
                valid_lines = []
                for line in geom.geoms:
                    coords = list(line.coords)
                    if len(coords) >= 2:
                        valid_coords = []
                        for coord in coords:
                            if len(coord) >= 2 and all(
                                isinstance(x, (int, float)) for x in coord[:2]
                            ):
                                valid_coords.append(coord[:2])

                        if len(valid_coords) >= 2:
                            from shapely.geometry import LineString

                            valid_lines.append(LineString(valid_coords))

                if valid_lines:
                    from shapely.geometry import MultiLineString

                    if len(valid_lines) == 1:
                        new_geom = valid_lines[0]
                    else:
                        new_geom = MultiLineString(valid_lines)

                    if new_geom.is_valid and not new_geom.is_empty:
                        row_copy = row.copy()
                        row_copy["geometry"] = new_geom
                        valid_boundaries.append(row_copy)
                        if new_geom != geom:
                            fixed_count += 1

            elif geom.geom_type in ["Point", "Polygon", "MultiPolygon"]:
                # Skip non-linear geometries
                continue

            else:
                # Try to fix invalid geometries with buffer
                try:
                    fixed_geom = geom.buffer(0)
                    if (
                        fixed_geom.is_valid
                        and not fixed_geom.is_empty
                        and fixed_geom.geom_type in ["LineString", "MultiLineString"]
                    ):
                        row_copy = row.copy()
                        row_copy["geometry"] = fixed_geom
                        valid_boundaries.append(row_copy)
                        fixed_count += 1
                except:
                    continue

        except Exception as e:
            logger.warning(f"Error processing boundary {idx}: {e}")
            continue

    if valid_boundaries:
        result = gpd.GeoDataFrame(valid_boundaries, crs=boundary_lines.crs)
        logger.info(
            f"Validated {len(result)} boundary lines from {len(boundary_lines)} original"
        )
        logger.info(f"Fixed {fixed_count} geometries")
        return result
    else:
        logger.error("No valid boundary lines found!")
        return gpd.GeoDataFrame(columns=boundary_lines.columns, crs=boundary_lines.crs)


def clean_regions(regions_gdf, min_area_threshold=1000):
    """
    Clean up regions by removing very small polygons and fixing invalid geometries.

    Args:
        regions_gdf (geopandas.GeoDataFrame): Regions to clean
        min_area_threshold (float): Minimum area threshold for keeping regions

    Returns:
        geopandas.GeoDataFrame: Cleaned regions
    """
    logger.info("Cleaning regions...")

    initial_count = len(regions_gdf)

    # Fix invalid geometries
    regions_gdf["geometry"] = regions_gdf["geometry"].buffer(0)

    # Calculate areas
    regions_gdf["area"] = regions_gdf.geometry.area

    # Remove very small regions
    regions_gdf = regions_gdf[regions_gdf["area"] > min_area_threshold]

    # Reset index
    regions_gdf = regions_gdf.reset_index(drop=True)

    logger.info(
        f"Cleaned regions: {initial_count} -> {len(regions_gdf)} (removed {initial_count - len(regions_gdf)} small regions)"
    )

    return regions_gdf


def filter_regions_with_powerplants(regions_gdf, powerplants_path):
    """
    Filter regions to keep only those that contain powerplants.
    
    Args:
        regions_gdf (geopandas.GeoDataFrame): Regions to filter
        powerplants_path (str): Path to powerplants CSV file
        
    Returns:
        geopandas.GeoDataFrame: Filtered regions containing powerplants
    """
    logger.info(f"Loading powerplants from: {powerplants_path}")
    
    try:
        # Load powerplants data
        powerplants_df = pd.read_csv(powerplants_path)
        logger.info(f"Loaded {len(powerplants_df)} powerplants")
        
        # Check for required columns
        if 'lat' not in powerplants_df.columns or 'lon' not in powerplants_df.columns:
            logger.error("Powerplants file must contain 'lat' and 'lon' columns")
            return regions_gdf
        
        # Remove rows with missing coordinates
        powerplants_df = powerplants_df.dropna(subset=['lat', 'lon'])
        logger.info(f"After removing missing coordinates: {len(powerplants_df)} powerplants")
        
        if len(powerplants_df) == 0:
            logger.warning("No powerplants with valid coordinates found")
            return regions_gdf
        
        # Create GeoDataFrame from powerplants
        powerplant_geometries = [Point(lon, lat) for lon, lat in zip(powerplants_df['lon'], powerplants_df['lat'])]
        powerplants_gdf = gpd.GeoDataFrame(
            powerplants_df, 
            geometry=powerplant_geometries, 
            crs='EPSG:4326'  # Assuming lat/lon coordinates are in WGS84
        )
        
        # Convert powerplants to same CRS as regions
        if regions_gdf.crs != powerplants_gdf.crs:
            powerplants_gdf = powerplants_gdf.to_crs(regions_gdf.crs)
            logger.info(f"Converted powerplants CRS from EPSG:4326 to {regions_gdf.crs}")
        
        # Find regions that contain powerplants
        regions_with_powerplants = []
        powerplant_count_per_region = []
        
        for idx, region in regions_gdf.iterrows():
            # Check which powerplants fall within this region
            powerplants_in_region = powerplants_gdf[powerplants_gdf.geometry.within(region.geometry)]
            
            if len(powerplants_in_region) > 0:
                regions_with_powerplants.append(region)
                powerplant_count_per_region.append(len(powerplants_in_region))
                logger.info(f"Region {region.get('region_id', idx)} contains {len(powerplants_in_region)} powerplants")
            else:
                logger.debug(f"Region {region.get('region_id', idx)} contains no powerplants - removing")
        
        if regions_with_powerplants:
            # Create new GeoDataFrame with only regions containing powerplants
            filtered_regions = gpd.GeoDataFrame(regions_with_powerplants, crs=regions_gdf.crs)
            filtered_regions['powerplant_count'] = powerplant_count_per_region
            filtered_regions = filtered_regions.reset_index(drop=True)
            
            logger.info(f"Filtered regions: {len(regions_gdf)} -> {len(filtered_regions)} (kept only regions with powerplants)")
            logger.info(f"Total powerplants in kept regions: {sum(powerplant_count_per_region)}")
            
            return filtered_regions
        else:
            logger.warning("No regions contain powerplants! Keeping all regions.")
            return regions_gdf
            
    except Exception as e:
        logger.error(f"Error filtering regions with powerplants: {e}")
        logger.warning("Continuing with unfiltered regions")
        return regions_gdf


def save_regions(regions_gdf, output_path):
    """
    Save regions to GeoJSON file.

    Args:
        regions_gdf (geopandas.GeoDataFrame): Regions to save
        output_path (str): Output file path
    """
    try:
        logger.info(f"Saving regions to: {output_path}")

        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {output_dir}")

        # Convert back to WGS84 for better map compatibility
        regions_wgs84 = regions_gdf.to_crs("EPSG:4326")

        # Save to GeoJSON in WGS84 format
        regions_wgs84.to_file(output_path, driver="GeoJSON")

        logger.info(f"Successfully saved {len(regions_gdf)} regions to {output_path}")

    except Exception as e:
        logger.error(f"Error saving regions: {e}")
        raise


if __name__ == "__main__":
    # Define file paths
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data" / "gis_data"
    results_dir = base_dir / "results"

    country_shapes_path = data_dir / "country_shapes.geojson"
    boundary_lines_path = (
        data_dir / "etys-boundary-gis-data-mar25" / "ETYS boundary GIS data Mar25.shp"
    )
    output_path_all = results_dir / "region_shapes.geojson"
    output_path_no_powerplants = results_dir / "region_shapes_no_powerplants.geojson"

    try:
        # Load data
        print("Loading country shapes...")
        country_shapes = load_country_shapes(country_shapes_path)

        print("\nCountry shapes info:")
        print(f"- Number of shapes: {len(country_shapes)}")
        print(f"- CRS: {country_shapes.crs}")
        print(f"- Columns: {list(country_shapes.columns)}")
        print(f"- Total area: {country_shapes.geometry.area.sum() / 1000000:.0f} km²")

        # Load boundary lines from shapefile
        print("\nLoading boundary lines...")
        raw_boundary_lines = load_boundary_lines(boundary_lines_path)

        print("\nRaw boundary lines info:")
        print(f"- Total features: {len(raw_boundary_lines)}")
        print(f"- Geometry types: {raw_boundary_lines.geometry.type.value_counts()}")
        print(f"- CRS: {raw_boundary_lines.crs}")
        if len(raw_boundary_lines.columns) > 1:
            print(f"- Columns: {list(raw_boundary_lines.columns)}")

        # Validate and clean boundary lines
        print("\nValidating boundary lines...")
        boundary_lines = validate_and_fix_boundary_data(raw_boundary_lines)

        if len(boundary_lines) == 0:
            logger.error("No valid boundary lines available for splitting!")
            print("ERROR: No valid boundary lines found. Check the ETYS data format.")
            exit(1)

        print("\nValidated boundary lines info:")
        print(f"- Valid features: {len(boundary_lines)}")
        print(f"- Geometry types: {boundary_lines.geometry.type.value_counts()}")
        print(
            f"- Length range: {boundary_lines.geometry.length.min():.0f} - {boundary_lines.geometry.length.max():.0f} meters"
        )

        # Sample some boundary properties
        for col in boundary_lines.columns:
            if col != "geometry" and boundary_lines[col].dtype == "object":
                unique_vals = boundary_lines[col].dropna().unique()
                if len(unique_vals) > 0 and len(unique_vals) <= 20:
                    print(f"- {col}: {list(unique_vals)[:10]}")

        # Create regions
        print("\nCreating regions...")
        regions = create_regions_from_boundaries(country_shapes, boundary_lines)

        print(f"\nRegions created: {len(regions)}")
        if len(regions) > 1:
            print(
                f"- Area range: {regions.geometry.area.min() / 1000000:.1f} - {regions.geometry.area.max() / 1000000:.1f} km²"
            )
            print(f"- Average area: {regions.geometry.area.mean() / 1000000:.1f} km²")

        # Clean regions with appropriate threshold (1 km²)
        min_area = 1000000  # 1 km² in square meters
        print(f"\nCleaning regions (removing regions < {min_area/1000000:.0f} km²)...")
        cleaned_regions = clean_regions(regions, min_area_threshold=min_area)

        # Save all cleaned regions (output 1: all regions with 1km² minimum)
        print(f"\nSaving all cleaned regions to: {output_path_all}")
        save_regions(cleaned_regions, output_path_all)

        # Filter regions to keep only those with powerplants (output 2: regions without powerplants removed)
        powerplants_path = base_dir / "data" / "powerplants_s_100.csv"
        print(f"\nFiltering regions to keep only those with powerplants...")
        print(f"Using powerplants data from: {powerplants_path}")
        regions_with_powerplants = filter_regions_with_powerplants(cleaned_regions, powerplants_path)

        # Save regions with powerplants only
        print(f"\nSaving regions with powerplants to: {output_path_no_powerplants}")
        save_regions(regions_with_powerplants, output_path_no_powerplants)

        # Print final summary
        print("\n" + "=" * 60)
        print("REGION CREATION SUMMARY")
        print("=" * 60)
        print(f"Input country shapes: {len(country_shapes)}")
        print(f"Raw boundary features: {len(raw_boundary_lines)}")
        print(f"Valid boundary features: {len(boundary_lines)}")
        print(f"Initial regions: {len(regions)}")
        print(f"Regions after cleaning: {len(cleaned_regions)}")
        print(f"Regions with powerplants: {len(regions_with_powerplants)}")
        print(f"Output file (all regions): {output_path_all}")
        print(f"Output file (powerplants only): {output_path_no_powerplants}")

        if len(cleaned_regions) > 1:
            print("\nAll regions summary:")
            print(f"  - Total regions: {len(cleaned_regions)}")
            area_range = [r.geometry.area / 1000000 for _, r in cleaned_regions.iterrows()]
            print(f"  - Area range: {min(area_range):.1f} - {max(area_range):.1f} km²")
            print(f"  - Average area: {sum(area_range)/len(area_range):.1f} km²")

        if len(regions_with_powerplants) > 1:
            print("\nRegions with powerplants details:")
            for i, region in regions_with_powerplants.iterrows():
                area_km2 = region.geometry.area / 1000000
                powerplant_count = region.get('powerplant_count', 'N/A')
                print(f"  - {region['region_id']}: {area_km2:.1f} km² ({powerplant_count} powerplants)")

        print("=" * 60)

    except Exception as e:
        logger.error(f"Error in main process: {e}")
        import traceback

        traceback.print_exc()
        raise
