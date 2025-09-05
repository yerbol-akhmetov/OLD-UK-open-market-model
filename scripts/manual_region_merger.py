#!/usr/bin/env python3
"""
Manual Region Merger Script

This script allows manual joining of specific regions from 1km2_region_shapes.geojson
based on provided region IDs.
"""

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_regions(input_file):
    """Load regions from GeoJSON file"""
    logger.info(f"Loading regions from: {input_file}")
    regions_gdf = gpd.read_file(input_file)
    logger.info(f"Loaded {len(regions_gdf)} regions")
    
    # Show available region IDs for reference
    if 'region_id' in regions_gdf.columns:
        region_ids = regions_gdf['region_id'].tolist()
        logger.info(f"Sample region IDs: {region_ids[:10]}")
        logger.info(f"Region ID type: {type(region_ids[0])}")
        
        # Extract numeric parts from region IDs for matching
        numeric_ids = []
        for rid in region_ids:
            # Try to extract number from region ID (e.g., "region_54" -> 54)
            import re
            numbers = re.findall(r'\d+', str(rid))
            if numbers:
                numeric_ids.append(int(numbers[-1]))  # Take the last number found
            else:
                numeric_ids.append(None)
        
        # Add numeric ID column for easier matching
        regions_gdf['numeric_id'] = numeric_ids
        logger.info(f"Extracted numeric IDs: {sorted([x for x in numeric_ids if x is not None])}")
        
    else:
        logger.info("No 'region_id' column found, using index as region ID")
        regions_gdf['region_id'] = regions_gdf.index + 1
        regions_gdf['numeric_id'] = regions_gdf.index + 1
    
    return regions_gdf

def merge_regions(regions_gdf, merge_groups):
    """
    Merge specified groups of regions
    
    Args:
        regions_gdf: GeoDataFrame containing regions
        merge_groups: List of lists, each containing region IDs to merge
    
    Returns:
        GeoDataFrame with merged regions
    """
    logger.info(f"Processing {len(merge_groups)} merge groups")
    
    # Create a copy to work with
    result_gdf = regions_gdf.copy()
    regions_to_remove = set()
    
    for i, group in enumerate(merge_groups):
        logger.info(f"Processing merge group {i+1}: regions {group}")
        
        # Find regions in this group
        group_regions = result_gdf[result_gdf['numeric_id'].isin(group)]
        
        if len(group_regions) == 0:
            logger.warning(f"No regions found for group {group}")
            continue
        
        if len(group_regions) < len(group):
            found_ids = group_regions['numeric_id'].tolist()
            missing_ids = [rid for rid in group if rid not in found_ids]
            logger.warning(f"Some regions not found in group {group}. Found: {found_ids}, Missing: {missing_ids}")
        
        if len(group_regions) < 2:
            logger.warning(f"Group {group} has less than 2 regions, skipping merge")
            continue
        
        # Get the first region as the base (will keep this one)
        base_region_idx = group_regions.index[0]
        base_region = group_regions.iloc[0]
        
        # Collect geometries to merge
        geometries_to_merge = [region.geometry for _, region in group_regions.iterrows()]
        
        # Merge geometries
        try:
            merged_geometry = unary_union(geometries_to_merge)
            logger.info(f"Successfully merged {len(geometries_to_merge)} geometries")
        except Exception as e:
            logger.error(f"Failed to merge geometries for group {group}: {e}")
            continue
        
        # Update the base region with merged geometry
        result_gdf.loc[base_region_idx, 'geometry'] = merged_geometry
        
        # Update area if column exists
        if 'area_km2' in result_gdf.columns:
            # Calculate new area (assuming CRS is in meters)
            new_area_km2 = merged_geometry.area / 1000000
            result_gdf.loc[base_region_idx, 'area_km2'] = new_area_km2
            logger.info(f"Updated area to {new_area_km2:.2f} km²")
        
        # Track merged region IDs
        merged_region_ids = ', '.join(map(str, group[1:]))  # All except the first
        if 'merged_regions' in result_gdf.columns:
            existing_merged = result_gdf.loc[base_region_idx, 'merged_regions']
            if pd.isna(existing_merged) or existing_merged == '':
                result_gdf.loc[base_region_idx, 'merged_regions'] = merged_region_ids
            else:
                result_gdf.loc[base_region_idx, 'merged_regions'] = f"{existing_merged}, {merged_region_ids}"
        else:
            result_gdf['merged_regions'] = ''
            result_gdf.loc[base_region_idx, 'merged_regions'] = merged_region_ids
        
        # Mark other regions in group for removal
        for region_id in group[1:]:  # All except the first
            region_indices = result_gdf[result_gdf['numeric_id'] == region_id].index
            regions_to_remove.update(region_indices)
        
        logger.info(f"Merged regions {group} into region {base_region['region_id']} (numeric: {base_region['numeric_id']})")
    
    # Remove merged regions
    if regions_to_remove:
        logger.info(f"Removing {len(regions_to_remove)} merged regions")
        result_gdf = result_gdf.drop(index=regions_to_remove)
    
    # Reset index
    result_gdf = result_gdf.reset_index(drop=True)
    
    logger.info(f"Final result: {len(regions_gdf)} -> {len(result_gdf)} regions")
    return result_gdf

def save_regions(regions_gdf, output_file):
    """Save regions to GeoJSON file"""
    logger.info(f"Saving {len(regions_gdf)} regions to: {output_file}")
    regions_gdf.to_file(output_file, driver='GeoJSON')
    logger.info("Save completed successfully")

def main():
    """Main function"""
    # Input and output files
    input_file = "results/region_shapes.geojson"
    output_file = "results/manually_merged_region_shapes.geojson"
    
    # Define merge groups as specified (updated list)
    merge_groups = [
        [61, 64],                                   # Join 61, 64
        [47, 48, 49],                               # Join 47, 48, 49
        [54, 55, 56],                               # Join 54, 55, 56
        [52, 53],                                   # Join 52, 53
        [41, 43],                                   # Join 41, 43
        [77, 78, 79],                               # Join 77, 78, 79
        [40, 44, 45],                               # Join 40, 44, 45
        [13, 16, 17],                               # Join 13, 16, 17
        [18, 19, 20, 21, 22, 23, 24, 31, 32, 33, 34, 94, 95, 96, 97, 98], # Join 18, 19, 20, 21, 22, 23, 24, 31, 32, 33, 34, 94, 95, 96, 97, 98
        [2, 3, 91, 92],                             # Join 2, 3, 91, 92
        [14, 15, 25, 26, 27, 28, 29, 30, 35, 36, 37, 38], # Join 14, 15, 25, 26, 27, 28, 29, 30, 35, 36, 37, 38
        [4, 5],                                     # Join 4, 5
        [62, 86, 87, 88],                           # Join 62, 86, 87, 88
        [65, 66, 67, 68, 69, 70, 71, 72, 73, 84],   # Join 65, 66, 67, 68, 69, 70, 71, 72, 73, 84
        [10, 11, 12],                               # Join 10, 11, 12
        [6, 7, 9],                                  # Join 6, 7, 9
        [39, 99],                                   # Join 39, 99
        [74, 75, 76]                                # Join 74, 75, 76
    ]
    
    logger.info("Starting manual region merger")
    logger.info(f"Merge groups: {merge_groups}")
    
    try:
        # Load regions
        regions_gdf = load_regions(input_file)
        
        # Perform merging
        merged_regions = merge_regions(regions_gdf, merge_groups)
        
        # Save results
        save_regions(merged_regions, output_file)
        
        logger.info("Manual region merging completed successfully!")
        logger.info(f"Output saved to: {output_file}")
        
        # Print summary
        original_count = len(regions_gdf)
        final_count = len(merged_regions)
        regions_removed = original_count - final_count
        logger.info(f"Summary: {original_count} -> {final_count} regions (removed {regions_removed} through merging)")
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        raise

if __name__ == "__main__":
    main()
