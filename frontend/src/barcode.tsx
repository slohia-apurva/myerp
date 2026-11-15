/** Code 128 (set B) barcodes for package labels, drawn as SVG: any handheld scanner or
 * phone camera reads them. Only printable ASCII is needed (package numbers like
 * PK-000241). */

// Bar and space widths of each symbol value 0-106 (106 is Stop).
const PATTERNS = [
  "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
  "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
  "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
  "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
  "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
  "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
  "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
  "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
  "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
  "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
  "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
];
const START_B = 104;
const CODE_C = 99; // switch to set C (in set B)
const CODE_B = 100; // switch to set B (in set C)
const STOP = 106;

/** The bars as a string of modules, "1" dark and "0" light (no quiet zone). */
export function code128(text: string): string {
  const values = [START_B];
  let inC = false;
  for (let i = 0; i < text.length; ) {
    // A run of 4 or more digits goes in pairs (set C), which keeps the label short.
    const run = /^\d*/.exec(text.slice(i))![0].length;
    if (!inC && run >= 4 && run % 2 === 0) {
      values.push(CODE_C);
      inC = true;
    }
    if (inC && run >= 2) {
      values.push(Number(text.slice(i, i + 2)));
      i += 2;
      continue;
    }
    if (inC) {
      values.push(CODE_B);
      inC = false;
    }
    const code = text.charCodeAt(i);
    if (code < 32 || code > 126) throw new Error(`Cannot put "${text[i]}" in a barcode.`);
    values.push(code - 32);
    i += 1;
  }
  const check = values.reduce((sum, v, i) => sum + v * (i === 0 ? 1 : i), 0) % 103;
  values.push(check, STOP);
  let modules = "";
  for (const v of values) {
    [...PATTERNS[v]].forEach((w, i) => {
      modules += (i % 2 === 0 ? "1" : "0").repeat(Number(w));
    });
  }
  return modules;
}

/** An SVG barcode filling its box; `height` in the SVG's own units. */
export function Barcode({ value, className }: { value: string; className?: string }) {
  const modules = code128(value);
  const quiet = 10;
  const bars: { x: number; w: number }[] = [];
  for (let i = 0; i < modules.length; i++) {
    if (modules[i] !== "1") continue;
    const start = i;
    while (modules[i + 1] === "1") i++;
    bars.push({ x: start + quiet, w: i - start + 1 });
  }
  return (
    <svg className={className} viewBox={`0 0 ${modules.length + quiet * 2} 40`} preserveAspectRatio="none" role="img" aria-label={`Barcode ${value}`}>
      {bars.map((b) => (
        <rect key={b.x} x={b.x} y={0} width={b.w} height={40} fill="#000" />
      ))}
    </svg>
  );
}
