export function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const units = ['KB', 'MB', 'GB', 'TB'];
  let scaled = bytes / 1024;
  let unit = units[0];

  for (let i = 1; i < units.length && scaled >= 1024; i += 1) {
    scaled /= 1024;
    unit = units[i];
  }

  return `${scaled.toFixed(scaled >= 10 ? 1 : 2)} ${unit}`;
}

const countFormat = new Intl.NumberFormat();

export function describeLoadedCount(loaded, total = null) {
  const noun = (count) => (count === 1 ? 'item' : 'items');
  if (total === null || total === undefined) {
    return `Loaded ${countFormat.format(loaded)} ${noun(loaded)}.`;
  }
  if (loaded >= total) {
    return `${countFormat.format(total)} ${noun(total)}.`;
  }
  return `Showing ${countFormat.format(loaded)} of ${countFormat.format(total)} ${noun(total)}.`;
}

export function formatDate(ts) {
  if (!ts) {
    return 'Unknown';
  }
  return new Date(Number(ts) * 1000).toLocaleString();
}
