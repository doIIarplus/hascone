// Compact meso display for modeled costs.
export const compactCost = value => {
  if(value==null || !Number.isFinite(Number(value)))return '—';
  const units=[[1e15,'Q'],[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'K']];
  const [size,suffix]=units.find(([size])=>Number(value)>=size)||[1,''];
  return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(Number(value)/size)+suffix;
};
