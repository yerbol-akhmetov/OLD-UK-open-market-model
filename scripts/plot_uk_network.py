#!/usr/bin/env python3
"""
Script to plot transmission lines from base.nc and regional shapes for UK only.
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import geopandas as gpd
import pandas as pd
import numpy as np
import re
from pathlib import Path
from shapely.geometry import Point
import pypsa


def load_pypsa_network(network_path):
    """Load PyPSA network from .nc file"""
    print(f"Loading PyPSA network from: {network_path}")
    network = pypsa.Network(network_path)
    print(f"Network loaded: {len(network.buses)} buses, {len(network.lines)} lines")
    return network


def filter_uk_components(network):
    """Filter network components to include only UK (GB) elements"""
    print("Filtering network for UK components...")
    
    # Filter buses for UK - assuming UK buses have country code 'GB'
    if 'country' in network.buses.columns:
        uk_buses = network.buses[network.buses['country'] == 'GB']
        print(f"Found {len(uk_buses)} UK buses using country filter")
    else:
        # Fallback: filter by coordinates (UK bounding box)
        # UK roughly: longitude -8 to 2, latitude 50 to 61
        uk_buses = network.buses[
            (network.buses['x'] >= -8) & (network.buses['x'] <= 2) &
            (network.buses['y'] >= 50) & (network.buses['y'] <= 61)
        ]
        print(f"Found {len(uk_buses)} UK buses using coordinate filter")
    
    # Filter lines that connect UK buses
    uk_lines = network.lines[
        (network.lines['bus0'].isin(uk_buses.index)) & 
        (network.lines['bus1'].isin(uk_buses.index))
    ]
    
    print(f"Found {len(uk_lines)} UK transmission lines")
    
    return uk_buses, uk_lines


def plot_uk_network_and_regions():
    """Create visualization of UK transmission network and manually merged regional shapes"""
    
    # Define file paths
    base_dir = Path(__file__).parent.parent
    network_path = base_dir / "resources" / "networks" / "base.nc"
    regions_path = base_dir / "results" / "manually_merged_region_shapes.geojson"
    
    # Check if files exist
    if not network_path.exists():
        print(f"Network file not found: {network_path}")
        # Try alternative locations
        alt_paths = [
            base_dir / "base.nc",
            base_dir / "networks" / "base.nc",
            base_dir / "results" / "base.nc"
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                network_path = alt_path
                print(f"Found network at: {network_path}")
                break
        else:
            print("No base.nc file found in any expected location!")
            return
    
    if not regions_path.exists():
        print(f"Regions file not found: {regions_path}")
        return
    
    # Load PyPSA network
    network = load_pypsa_network(network_path)
    
    # Filter for UK components
    uk_buses, uk_lines = filter_uk_components(network)
    
    if len(uk_buses) == 0:
        print("No UK buses found in the network!")
        return
    
    # Load manually merged regional shapes
    print(f"Loading manually merged regional shapes from: {regions_path}")
    regions_gdf = gpd.read_file(regions_path)
    print(f"Loaded {len(regions_gdf)} manually merged regions")
    
    # Convert regions to a nice projection for UK visualization (British National Grid)
    if regions_gdf.crs != "EPSG:27700":
        print(f"Converting regions from {regions_gdf.crs} to EPSG:27700 (British National Grid)")
        regions_gdf = regions_gdf.to_crs("EPSG:27700")
    
    # Convert bus coordinates to the same projection
    uk_buses_proj = uk_buses.copy()
    if 'x' in uk_buses.columns and 'y' in uk_buses.columns:
        # Create GeoDataFrame from bus coordinates
        bus_points = gpd.GeoDataFrame(
            uk_buses, 
            geometry=[Point(x, y) for x, y in zip(uk_buses['x'], uk_buses['y'])],
            crs="EPSG:4326"  # Assuming lon/lat coordinates
        )
        # Convert to British National Grid
        bus_points_proj = bus_points.to_crs("EPSG:27700")
        uk_buses_proj['x_proj'] = bus_points_proj.geometry.x
        uk_buses_proj['y_proj'] = bus_points_proj.geometry.y
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(15, 18))
    
    # Generate different colors for each region using graph coloring approach
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    from collections import defaultdict
    
    # Build adjacency graph to identify neighboring regions
    adjacency = defaultdict(set)
    
    print("Building adjacency graph for better color assignment...")
    for i, region1 in regions_gdf.iterrows():
        for j, region2 in regions_gdf.iterrows():
            if i != j:
                # Check if regions are adjacent (share boundary)
                if region1.geometry.touches(region2.geometry):
                    adjacency[i].add(j)
                    adjacency[j].add(i)
    
    # Simple graph coloring algorithm
    def assign_colors_greedy(adjacency, n_regions):
        colors = {}
        # Define a palette of light, pastel colors with different tones and shades
        color_palette = [
            '#e6f3ff', '#cce7ff', '#b3dbff', '#99cfff', '#80c3ff', '#66b7ff',  # Light blues
            '#e6ffe6', '#ccffcc', '#b3ffb3', '#99ff99', '#80ff80', '#66ff66',  # Light greens
            '#ffe6ff', '#ffccff', '#ffb3ff', '#ff99ff', '#ff80ff', '#ff66ff',  # Light magentas
            '#fff0e6', '#ffe6cc', '#ffccb3', '#ffb399', '#ff9980', '#ff8066',  # Light oranges
            '#f0e6ff', '#e6ccff', '#ddb3ff', '#d399ff', '#ca80ff', '#c066ff',  # Light purples
            '#e6fff0', '#ccffe6', '#b3ffcc', '#99ffb3', '#80ff99', '#66ff80',  # Light mint greens
            '#fffce6', '#fff9cc', '#fff6b3', '#fff399', '#fff080', '#ffed66',  # Light yellows
            '#e6f7ff', '#ccefff', '#b3e7ff', '#99dfff', '#80d7ff', '#66cfff',  # Light sky blues
            '#f7e6ff', '#efccff', '#e7b3ff', '#df99ff', '#d780ff', '#cf66ff',  # Light lavenders
            '#e6ffe6', '#ccf5cc', '#b3ebb3', '#99e199', '#80d780', '#66cd66',  # Light sage greens
            '#ffe6f7', '#ffccef', '#ffb3e7', '#ff99df', '#ff80d7', '#ff66cf',  # Light pinks
            '#f0ffe6', '#e6ffcc', '#dbffb3', '#d1ff99', '#c7ff80', '#bdff66'   # Light lime greens
        ]
        
        for region_idx in range(n_regions):
            # Find colors already used by neighbors
            neighbor_colors = set()
            for neighbor_idx in adjacency[region_idx]:
                if neighbor_idx in colors:
                    neighbor_colors.add(colors[neighbor_idx])
            
            # Assign first available color that's not used by neighbors
            for color_idx, color in enumerate(color_palette):
                if color_idx not in neighbor_colors:
                    colors[region_idx] = color_idx
                    break
            else:
                # Fallback if we run out of distinct colors
                colors[region_idx] = region_idx % len(color_palette)
        
        return colors, color_palette
    
    # Assign colors using graph coloring
    n_regions = len(regions_gdf)
    region_color_indices, color_palette = assign_colors_greedy(adjacency, n_regions)
    
    print(f"Assigned colors to {n_regions} regions with {len(set(region_color_indices.values()))} distinct colors")
    
    # Plot each region with its assigned color
    for idx, (_, region) in enumerate(regions_gdf.iterrows()):
        color_idx = region_color_indices[idx]
        color = color_palette[color_idx]
        
        region_gdf = gpd.GeoDataFrame([region], crs=regions_gdf.crs)
        region_gdf.plot(
            ax=ax,
            facecolor=color,
            edgecolor='darkgray',
            alpha=0.9,
            linewidth=1.2
        )
    
    # Plot transmission lines using projected coordinates
    if len(uk_lines) > 0:
        print(f"Plotting {len(uk_lines)} transmission lines...")
        for idx, line in uk_lines.iterrows():
            bus0_name = line['bus0']
            bus1_name = line['bus1']
            
            if bus0_name in uk_buses_proj.index and bus1_name in uk_buses_proj.index:
                bus0 = uk_buses_proj.loc[bus0_name]
                bus1 = uk_buses_proj.loc[bus1_name]
                
                if 'x_proj' in bus0.index and 'x_proj' in bus1.index:
                    ax.plot(
                        [bus0['x_proj'], bus1['x_proj']], 
                        [bus0['y_proj'], bus1['y_proj']], 
                        'red', 
                        linewidth=1.5, 
                        alpha=0.9,
                        zorder=3
                    )
    
    # Plot buses using projected coordinates
    if len(uk_buses_proj) > 0 and 'x_proj' in uk_buses_proj.columns:
        ax.scatter(
            uk_buses_proj['x_proj'], 
            uk_buses_proj['y_proj'], 
            c='black', 
            s=40, 
            alpha=0.9,
            zorder=5,
            edgecolors='white',
            linewidth=0.5
        )
        print(f"Plotted {len(uk_buses_proj)} buses")
    
    # Customize the plot
    ax.set_title('UK Transmission Network and Manually Merged Regional Boundaries', 
                fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Easting (m)', fontsize=12)
    ax.set_ylabel('Northing (m)', fontsize=12)
    
    # Set equal aspect ratio for projected coordinates
    ax.set_aspect('equal')
    
    # Add grid
    ax.grid(True, alpha=0.3)
    
    # Add legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color='red', lw=2, label='Transmission Lines'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='black', markersize=8, 
               markeredgecolor='white', label='Buses'),
        plt.Rectangle((0, 0), 1, 1, facecolor='lightblue', edgecolor='black', 
                     alpha=0.7, label='Merged Regions')
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=10)
    
    # Add statistics text
    stats_text = f"""UK Network Statistics:
• Merged Regions: {len(regions_gdf)}
• Buses: {len(uk_buses)}
• Lines: {len(uk_lines)}
• Projection: EPSG:27700 (BNG)"""
    
    ax.text(0.98, 0.98, stats_text, transform=ax.transAxes, 
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray'))
    
    # Add region labels if there aren't too many
    if len(regions_gdf) <= 30:  # Only label if reasonable number of regions
        for idx, region in regions_gdf.iterrows():
            # Get centroid for label placement
            centroid = region.geometry.centroid
            region_id = region.get('region_id', f'Region_{idx}')
            
            # Extract numeric part for cleaner labeling
            if isinstance(region_id, str):
                import re
                numbers = re.findall(r'\d+', region_id)
                if numbers:
                    region_id = numbers[-1]
            
            ax.annotate(
                str(region_id), 
                xy=(centroid.x, centroid.y), 
                ha='center', va='center',
                fontsize=8, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='gray'),
                zorder=4
            )
    
    plt.tight_layout()
    
    # Create plots directory if it doesn't exist
    plots_dir = base_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    
    # Save the plot
    output_path = plots_dir / "uk_manually_merged_regions_plot.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Plot saved to: {output_path}")
    
    # Also save as PDF for better quality
    output_path_pdf = plots_dir / "uk_manually_merged_regions_plot.pdf"
    plt.savefig(output_path_pdf, bbox_inches='tight')
    print(f"Plot also saved as PDF to: {output_path_pdf}")
    
    # Close the figure to free memory
    plt.close()


if __name__ == "__main__":
    plot_uk_network_and_regions()
