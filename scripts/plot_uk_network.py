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
    """Create visualization of UK transmission network and regional shapes"""
    
    # Define file paths
    base_dir = Path(__file__).parent.parent
    network_path = base_dir / "resources" / "networks" / "base.nc"
    regions_path = base_dir / "data" / "gis_data" / "region_shapes_powerplants.geojson"
    
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
    
    # Load regional shapes
    print(f"Loading regional shapes from: {regions_path}")
    regions_gdf = gpd.read_file(regions_path)
    print(f"Loaded {len(regions_gdf)} regions")
    
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
    fig, ax = plt.subplots(figsize=(12, 14))
    
    # Plot regional boundaries
    regions_gdf.plot(
        ax=ax,
        facecolor='lightblue',
        edgecolor='darkblue',
        alpha=0.6,
        linewidth=1.5
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
                        linewidth=1.2, 
                        alpha=0.8
                    )
    
    # Plot buses using projected coordinates
    if len(uk_buses_proj) > 0 and 'x_proj' in uk_buses_proj.columns:
        ax.scatter(
            uk_buses_proj['x_proj'], 
            uk_buses_proj['y_proj'], 
            c='black', 
            s=30, 
            alpha=0.8,
            zorder=5
        )
        print(f"Plotted {len(uk_buses_proj)} buses")
    
    # Customize the plot
    ax.set_title('UK Transmission Network and Regional Boundaries', fontsize=16, fontweight='bold')
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
        Line2D([0], [0], marker='o', color='w', markerfacecolor='black', markersize=8, label='Buses'),
        plt.Rectangle((0, 0), 1, 1, facecolor='lightblue', edgecolor='darkblue', alpha=0.6, label='Regions')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    # Add statistics text
    stats_text = f"""UK Network Statistics:
• Regions: {len(regions_gdf)}
• Buses: {len(uk_buses)}
• Lines: {len(uk_lines)}
• Projection: EPSG:27700 (BNG)"""
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    
    # Create plots directory if it doesn't exist
    plots_dir = base_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    
    # Save the plot
    output_path = plots_dir / "uk_transmission_network_plot.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Plot saved to: {output_path}")
    
    # Close the figure to free memory
    plt.close()


if __name__ == "__main__":
    plot_uk_network_and_regions()
