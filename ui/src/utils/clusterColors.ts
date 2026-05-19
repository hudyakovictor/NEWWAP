// Consistent color assignment for persona clusters
const CLUSTER_COLORS = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#06b6d4', // cyan
  '#3b82f6', // blue
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#f43f5e', // rose
  '#84cc16', // lime
];

const colorMap = new Map<string, string>();

/**
 * Get a consistent color for a persona cluster based on its ID.
 * Uses a hash function to assign colors deterministically.
 * 
 * @param personaId - The persona ID to get a color for
 * @returns A hex color code
 */
export function getClusterColor(personaId: string): string {
  if (colorMap.has(personaId)) {
    return colorMap.get(personaId)!;
  }
  
  // Assign a color based on hash of persona_id
  let hash = 0;
  for (let i = 0; i < personaId.length; i++) {
    hash = personaId.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  const colorIndex = Math.abs(hash) % CLUSTER_COLORS.length;
  const color = CLUSTER_COLORS[colorIndex];
  colorMap.set(personaId, color);
  return color;
}

/**
 * Reset the color mapping cache.
 * Useful for testing or when you want to regenerate colors.
 */
export function resetColorMap(): void {
  colorMap.clear();
}
