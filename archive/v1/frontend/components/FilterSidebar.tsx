"use client";

import { useState } from "react";

export type WFHFilters = {
  // Derived attributes
  has_wifi?: string[];
  has_outlets?: string[];
  is_laptop_friendly?: string[];
  noise_level?: string[];
  seating_availability?: string[];
  seating_comfort?: string[];
  open_after_7pm?: string[];
  // Place detail attributes
  restroom?: boolean;
  outdoorSeating?: boolean;
  servesCoffee?: boolean;
};

type FilterSidebarProps = {
  filters: WFHFilters;
  onFiltersChange: (filters: WFHFilters) => void;
};

export default function FilterSidebar({ filters, onFiltersChange }: FilterSidebarProps) {
  const [isOpen, setIsOpen] = useState(true);

  const updateFilter = (key: keyof WFHFilters, value: any) => {
    onFiltersChange({
      ...filters,
      [key]: value,
    });
  };

  const toggleArrayFilter = (key: keyof WFHFilters, value: string) => {
    const current = filters[key] as string[] || [];
    const updated = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    updateFilter(key, updated.length > 0 ? updated : undefined);
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        zIndex: 10,
        background: "white",
        padding: 16,
        borderRadius: 8,
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        width: isOpen ? 280 : 60,
        transition: "width 0.3s ease",
        maxHeight: "90vh",
        overflowY: "auto",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: isOpen ? 12 : 0,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
          {isOpen ? "WFH Filters" : "⚙️"}
        </h3>
        <button
          onClick={() => setIsOpen(!isOpen)}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            fontSize: 18,
            padding: 4,
          }}
        >
          {isOpen ? "−" : "+"}
        </button>
      </div>

      {isOpen && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* WiFi Filter */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, display: "block" }}>
              WiFi
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {["free", "paid", "none"].map((value) => (
                <label key={value} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={filters.has_wifi?.includes(value) || false}
                    onChange={() => toggleArrayFilter("has_wifi", value)}
                  />
                  {value.charAt(0).toUpperCase() + value.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Outlets Filter */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, display: "block" }}>
              Outlets
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {["many", "few", "none"].map((value) => (
                <label key={value} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={filters.has_outlets?.includes(value) || false}
                    onChange={() => toggleArrayFilter("has_outlets", value)}
                  />
                  {value.charAt(0).toUpperCase() + value.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Laptop Friendly */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, display: "block" }}>
              Laptop Friendly
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {["yes", "mixed", "no"].map((value) => (
                <label key={value} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={filters.is_laptop_friendly?.includes(value) || false}
                    onChange={() => toggleArrayFilter("is_laptop_friendly", value)}
                  />
                  {value.charAt(0).toUpperCase() + value.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Noise Level */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, display: "block" }}>
              Noise Level
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {["quiet", "mixed", "loud"].map((value) => (
                <label key={value} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                  <input
                    type="checkbox"
                    checked={filters.noise_level?.includes(value) || false}
                    onChange={() => toggleArrayFilter("noise_level", value)}
                  />
                  {value.charAt(0).toUpperCase() + value.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Place Detail Attributes */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, display: "block" }}>
              Amenities
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={filters.restroom || false}
                  onChange={(e) => updateFilter("restroom", e.target.checked || undefined)}
                />
                Restroom
              </label>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={filters.outdoorSeating || false}
                  onChange={(e) => updateFilter("outdoorSeating", e.target.checked || undefined)}
                />
                Outdoor Seating
              </label>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={filters.servesCoffee || false}
                  onChange={(e) => updateFilter("servesCoffee", e.target.checked || undefined)}
                />
                Serves Coffee
              </label>
            </div>
          </div>

          {/* Clear Filters */}
          <button
            onClick={() => onFiltersChange({})}
            style={{
              padding: "8px 12px",
              background: "#f0f0f0",
              border: "1px solid #ddd",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Clear Filters
          </button>
        </div>
      )}
    </div>
  );
}

