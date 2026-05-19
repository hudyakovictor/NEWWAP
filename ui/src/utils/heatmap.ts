/**
 * Generate heatmap colors for vertex deltas.
 * Interpolates from blue (low delta) to red (high delta).
 * 
 * @param vertexDeltas - Array of delta values for each vertex
 * @param maxExpectedDelta - Maximum expected delta for normalization (default: 5.0)
 * @returns Float32Array of RGB values (3 values per vertex)
 */
export function generateHeatmapColors(
  vertexDeltas: number[], 
  maxExpectedDelta: number = 5.0
): Float32Array {
  const colors = new Float32Array(vertexDeltas.length * 3);
  
  for (let i = 0; i < vertexDeltas.length; i++) {
    // Normalize delta from 0 to 1
    const normalized = Math.min(vertexDeltas[i] / maxExpectedDelta, 1.0);
    
    // Blue (0,0,1) -> Cyan (0,1,1) -> Green (0,1,0) -> Yellow (1,1,0) -> Red (1,0,0)
    let r = 0, g = 0, b = 0;
    if (normalized < 0.25) {
      r = 0; g = normalized * 4; b = 1;
    } else if (normalized < 0.5) {
      r = 0; g = 1; b = 1 - (normalized - 0.25) * 4;
    } else if (normalized < 0.75) {
      r = (normalized - 0.5) * 4; g = 1; b = 0;
    } else {
      r = 1; g = 1 - (normalized - 0.75) * 4; b = 0;
    }

    colors[i * 3] = r;
    colors[i * 3 + 1] = g;
    colors[i * 3 + 2] = b;
  }
  return colors;
}
