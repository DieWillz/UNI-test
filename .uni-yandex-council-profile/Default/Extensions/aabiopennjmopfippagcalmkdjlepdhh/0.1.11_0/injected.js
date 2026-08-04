(function(){"use strict";function X(e){const t=Array.isArray(e.skills)?e.skills.map(s=>({name:String(s&&s.name?s.name:"skill"),content:String(s&&s.content?s.content:"")})).filter(s=>s.content.trim().length>0):[],n=Array.isArray(e.memories)?e.memories.map(s=>({key:U(s&&s.key),value:String(s&&s.value?s.value:""),importance:$(s&&s.importance)})).filter(s=>s.key&&s.value.trim().length>0):[],r=F(e.activeProject),c=(Array.isArray(e.systemPromptEntries)?e.systemPromptEntries:[]).map(s=>({id:String(s&&s.id?s.id:""),content:String(s&&s.content?s.content:""),enabled:s&&typeof s.enabled=="boolean"?s.enabled:!0,schedule:q(s&&s.schedule)})).filter(s=>s.id&&s.content.trim().length>0&&s.enabled),u=Array.isArray(e.mcpToolSchemas)?e.mcpToolSchemas.map(s=>({serverName:String(s.serverName||""),serverUrl:String(s.serverUrl||""),toolName:String(s.toolName||""),description:String(s.description||""),inputSchema:s.inputSchema||{}})).filter(s=>s.serverName&&s.toolName):[];return{systemPrompt:String(e.systemPrompt||""),systemPromptEntries:c,skills:t,memories:n,activeCharacter:e.activeCharacter||null,preferredLang:String(e.preferredLang||""),disableSystemPrompt:!!e.disableSystemPrompt,disableMemory:!!e.disableMemory,systemPromptInjectionFrequency:String(e.systemPromptInjectionFrequency||"first"),systemPromptInjectionInterval:Number(e.systemPromptInjectionInterval)||3,activeProject:r,projectRagEnabled:!!e.projectRagEnabled,projectRagLimit:Number(e.projectRagLimit)||5,injectSystemDateTime:!!e.injectSystemDateTime,deepResearch:R(e.deepResearch),mcpToolSchemas:u,mcpInlineMaxChars:Number(e.mcpInlineMaxChars)||8e3,modelInputLimits:e.modelInputLimits||{}}}function R(e){return!e||typeof e!="object"?{enabled:!1,runId:""}:{enabled:!!e.enabled,runId:String(e.runId||"").trim()}}function F(e){if(!e||typeof e!="object")return null;const t=String(e.name||"").trim(),n=String(e.instructions||""),r=Array.isArray(e.files)?e.files.map(i=>({name:String(i&&i.name?i.name:"file"),content:String(i&&i.content?i.content:"")})).filter(i=>i.content.length>0):[];return t?{name:t,instructions:n,files:r}:null}function q(e){if(!e||typeof e!="object")return{type:"first",everyNTurns:1};const t=String(e.type||"first");return{type:["first","always","interval"].includes(t)?t:"first",everyNTurns:Math.max(1,Math.floor(Number(e.everyNTurns)||3))}}function U(e){return String(e||"").trim().toLowerCase().replace(/[^a-z0-9_]/g,"")}function $(e){return String(e||"called").toLowerCase()==="always"?"always":"called"}const H=`
## SheetJS (XLSX) Library Reference

### GLOBAL AVAILABILITY
- XLSX is ALREADY globally available as \`window.XLSX\` in the sandbox.
- Do NOT use \`import\`, \`require\`, or \`const XLSX = ...\`.
- Just call \`XLSX.utils.book_new()\`, \`XLSX.utils.json_to_sheet()\`, etc. directly.

### CORRECT API (most common operations)

1. CREATE WORKBOOK:
   const wb = XLSX.utils.book_new();

2. CREATE SHEET FROM DATA:
   // From array of objects (column headers auto-detected):
   const ws = XLSX.utils.json_to_sheet([
     { Name: "Alice", Age: 30 },
     { Name: "Bob", Age: 25 }
   ]);
   // From array of arrays (first row = headers):
   const ws2 = XLSX.utils.aoa_to_sheet([
     ["Name", "Age"],
     ["Alice", 30],
     ["Bob", 25]
   ]);

3. APPEND SHEET TO WORKBOOK:
   XLSX.utils.book_append_sheet(wb, ws, "SheetName");

4. COLUMN WIDTHS (optional but recommended):
   ws["!cols"] = [{ wch: 20 }, { wch: 10 }];

5. SAVE \u2014 ALWAYS end with:
   XLSX.writeFile(wb, "filename.xlsx");
   // CRITICAL: This triggers the download. Without it, nothing happens.

### COMPLETE MINIMAL EXAMPLE:
const wb = XLSX.utils.book_new();
const ws = XLSX.utils.json_to_sheet([
  { Product: "Widget", Price: 9.99, Stock: 42 },
  { Product: "Gadget", Price: 24.99, Stock: 17 }
]);
ws["!cols"] = [{ wch: 15 }, { wch: 10 }, { wch: 10 }];
XLSX.utils.book_append_sheet(wb, ws, "Products");
XLSX.writeFile(wb, "products.xlsx");

### COMMON MISTAKES TO AVOID:
- \u2717 \`const XLSX = require('xlsx')\` \u2014 NOT available, don't use require
- \u2717 \`const XLSX = ...\` \u2014 XLSX is already defined, redeclaring causes error
- \u2717 \`XLSX.write(wb, ...)\` without type \u2014 use \`XLSX.writeFile(wb, name)\` for download
- \u2717 \`for each row manually\` \u2014 use json_to_sheet or aoa_to_sheet
- \u2717 Forgetting \`XLSX.utils.book_append_sheet()\` \u2014 the sheet must be added to workbook
- \u2717 \`await XLSX.writeFile()\` \u2014 writeFile is synchronous, no await needed
- \u2717 Browser APIs like \`document.getElementById\`, \`fetch\`, \`Blob\` \u2014 NOT available in sandbox

### CELL STYLING (limited support):
// Cell object in sheet:
ws["A1"] = { t: "s", v: "Header", s: { font: { bold: true } } };
// But for simplicity, prefer json_to_sheet or aoa_to_sheet with post-processing.

### MULTIPLE SHEETS:
const wb = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(data1), "Sheet1");
XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(data2), "Sheet2");
XLSX.writeFile(wb, "report.xlsx");

### FORMULAS:
const ws = XLSX.utils.aoa_to_sheet([
  ["Item", "Price", "Qty", "Total"],
  ["A", 10, 2, { t: "n", f: "B2*C2" }]
]);
`.trim(),J=`
## PptxGenJS Library Reference (PowerPoint)

### GLOBAL AVAILABILITY
- PptxGenJS is ALREADY globally available as \`window.PptxGenJS\` and \`window.pptxgen\` in the sandbox.
- Do NOT use \`import\`, \`require\`, or \`const PptxGenJS = ...\`.
- Just call \`new PptxGenJS()\` directly.

### CORRECT API

1. CREATE PRESENTATION:
   const pptx = new PptxGenJS();

2. CONFIGURE (optional):
   pptx.author = "Better DeepSeek";
   pptx.title = "Presentation Title";
   pptx.layout = "LAYOUT_WIDE"; // 16:9

3. ADD A SLIDE:
   const slide = pptx.addSlide();

4. ADD CONTENT TO SLIDE:
   // Text:
   slide.addText("Hello World", { x: 1, y: 1, w: 8, h: 1, fontSize: 24 });

   // Multi-line / bullet points:
   slide.addText([
     { text: "Main Title", options: { fontSize: 28, bold: true } },
     { text: "Subtitle text", options: { fontSize: 18 } }
   ], { x: 0.5, y: 0.5, w: 9, h: 2 });

   // Table:
   slide.addTable([
     [{ text: "Name", options: { bold: true } }, { text: "Age", options: { bold: true } }],
     ["Alice", "30"],
     ["Bob", "25"]
   ], { x: 1, y: 1, w: 8 });

   // Chart (bar, line, pie, etc.):
   slide.addChart(pptx.charts.BAR, [
     { name: "Sales", labels: ["Q1","Q2","Q3","Q4"], values: [100, 150, 130, 200] }
   ], { x: 1, y: 1, w: 8, h: 4 });

   // Image from URL:
   // slide.addImage({ path: "https://example.com/image.png", x: 1, y: 1, w: 4, h: 3 });

   // Shape:
   slide.addShape(pptx.shapes.RECTANGLE, { x: 1, y: 1, w: 4, h: 3, fill: { color: "4472C4" } });

5. SAVE \u2014 ALWAYS end with:
   await pptx.writeFile({ fileName: "Presentation.pptx" });
   // CRITICAL: Without this call, no file is generated. Must be awaited.

### COMPLETE MINIMAL EXAMPLE:
const pptx = new PptxGenJS();
pptx.title = "Project Plan";
pptx.layout = "LAYOUT_WIDE";

const slide1 = pptx.addSlide();
slide1.addText("Project Plan 2026", { x: 1, y: 1.5, w: 8, h: 1.5, fontSize: 36, bold: true, color: "1e3a8a", align: "center" });
slide1.addText("Prepared by Better DeepSeek", { x: 1, y: 3.5, w: 8, h: 0.8, fontSize: 16, align: "center" });

const slide2 = pptx.addSlide();
slide2.addText("Timeline", { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 28, bold: true });
slide2.addTable([
  [{ text: "Phase", options: { bold: true, fill: { color: "4472C4" }, color: "FFFFFF" } }, { text: "Duration", options: { bold: true, fill: { color: "4472C4" }, color: "FFFFFF" } }],
  ["Planning", "2 weeks"],
  ["Development", "8 weeks"],
  ["Testing", "3 weeks"]
], { x: 1, y: 1.5, w: 8 });

const slide3 = pptx.addSlide();
slide3.addText("Budget Overview", { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 28, bold: true });
slide3.addChart(pptx.charts.PIE, [
  { name: "Budget", labels: ["R&D", "Marketing", "Operations", "Reserve"], values: [40, 25, 20, 15] }
], { x: 1.5, y: 1.5, w: 7, h: 4 });

await pptx.writeFile({ fileName: "ProjectPlan.pptx" });

### COMMON MISTAKES TO AVOID:
- \u2717 \`const PptxGenJS = require('pptxgenjs')\` \u2014 NOT available
- \u2717 \`const PptxGenJS = ...\` \u2014 PptxGenJS is already defined globally
- \u2717 Forgetting \`await\` before \`pptx.writeFile()\` \u2014 it's async, must be awaited
- \u2717 \`pptx.save()\` \u2014 wrong method, use \`pptx.writeFile({ fileName: ... })\`
- \u2717 \`slide.addText("text", x, y, w, h)\` \u2014 wrong! Second arg is an options object
- \u2717 Using \`document.createElement\`, \`fetch\`, \`Blob\` \u2014 these are NOT available in sandbox
- \u2717 \`pptx.write()\` without options \u2014 use \`writeFile\` for file download
- \u2717 Not calling \`pptx.writeFile\` at all \u2014 the most common reason for "no output"

### POSITIONING HELP:
- Slide dimensions: LAYOUT_WIDE = 10" x 5.625", LAYOUT_STANDARD = 10" x 7.5"
- All positions in inches: { x: 0.5, y: 0.5, w: 9, h: 1 }
- (0,0) = top-left corner

### CHART TYPES:
pptx.charts.BAR, pptx.charts.COLUMN, pptx.charts.LINE, pptx.charts.PIE,
pptx.charts.DOUGHNUT, pptx.charts.SCATTER, pptx.charts.AREA, pptx.charts.RADAR

### SHAPES:
pptx.shapes.RECTANGLE, pptx.shapes.OVAL, pptx.shapes.LINE, pptx.shapes.RIGHT_TRIANGLE,
pptx.shapes.PENTAGON, pptx.shapes.HEXAGON, pptx.shapes.CHEVRON, pptx.shapes.STAR_5_POINT
`.trim(),G=`
## docx Library Reference (Word Documents)

### GLOBAL AVAILABILITY
- The \`docx\` library is ALREADY globally available as \`window.docx\`, \`window.DOCX\`, and \`window.Packer\`.
- All library exports are also available as globals: \`Document\`, \`Paragraph\`, \`TextRun\`, \`Table\`, etc.
- Do NOT use \`import\`, \`require\`, or \`const docx = ...\` / \`const DOCX = ...\`.
- Use \`DOCX.save(doc, "filename.docx")\` to trigger download.

### CORRECT API

1. DESTRUCTURE NEEDED CLASSES (optional, for cleaner code):
   const { Document, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel, AlignmentType, BorderStyle, WidthType } = DOCX;

2. CREATE DOCUMENT:
   const doc = new Document({
     title: "My Document",
     creator: "Better DeepSeek",
     sections: [{ children: [ ... ] }]
   });

3. CONTENT ELEMENTS (use inside children array):

   // Simple paragraph:
   new Paragraph({ children: [new TextRun("Hello World")] })

   // Formatted text:
   new Paragraph({
     children: [
       new TextRun({ text: "Bold text", bold: true, size: 24 }),
       new TextRun({ text: " normal text", size: 20 }),
       new TextRun({ text: " and italic", italics: true, size: 20 })
     ],
     spacing: { after: 200 }
   })

   // Heading:
   new Paragraph({
     text: "Chapter 1",
     heading: HeadingLevel.HEADING_1
   })

   // Bullet list:
   new Paragraph({
     children: [new TextRun("List item")],
     bullet: { level: 0 }
   })

   // Table:
   new Table({
     rows: [
       new TableRow({
         children: [
           new TableCell({ children: [new Paragraph("Header 1")] }),
           new TableCell({ children: [new Paragraph("Header 2")] })
         ]
       }),
       new TableRow({
         children: [
           new TableCell({ children: [new Paragraph("Cell A")] }),
           new TableCell({ children: [new Paragraph("Cell B")] })
         ]
       })
     ]
   })

   // Page break:
   new Paragraph({ pageBreakBefore: true })

4. SAVE \u2014 ALWAYS end with:
   await DOCX.save(doc, "filename.docx");
   // Alternatively: const blob = await DOCX.Packer.toBlob(doc);
   // CRITICAL: Without DOCX.save(), no file is generated.

### COMPLETE MINIMAL EXAMPLE:
const { Document, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell } = DOCX;

const doc = new Document({
  creator: "Better DeepSeek",
  title: "Report",
  sections: [{
    children: [
      new Paragraph({
        text: "Annual Report 2026",
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "This is the introduction paragraph. ", size: 22 }),
          new TextRun({ text: "Important note in bold.", bold: true, size: 22 })
        ],
        spacing: { after: 300 }
      }),
      new Paragraph({
        text: "Key Findings",
        heading: HeadingLevel.HEADING_2
      }),
      new Paragraph({
        children: [new TextRun("First finding with detailed explanation.")],
        bullet: { level: 0 }
      }),
      new Paragraph({
        children: [new TextRun("Second finding.")],
        bullet: { level: 0 }
      }),
      new Table({
        rows: [
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph("Metric")] }),
              new TableCell({ children: [new Paragraph("Value")] })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph("Revenue")] }),
              new TableCell({ children: [new Paragraph("$1.2M")] })
            ]
          })
        ]
      })
    ]
  }]
});

await DOCX.save(doc, "AnnualReport.docx");

### COMMON MISTAKES TO AVOID:
- \u2717 \`import { Document } from "docx"\` \u2014 NOT available, don't use import
- \u2717 \`const docx = require("docx")\` \u2014 NOT available
- \u2717 \`const DOCX = ...\` or \`const docx = ...\` \u2014 DOCX/docx is already globally defined
- \u2717 \`new Docx()\` \u2014 wrong! Use \`new Document()\` from the library
- \u2717 \`doc.save("filename.docx")\` \u2014 use \`DOCX.save(doc, "filename.docx")\`
- \u2717 Forgetting \`await\` before \`DOCX.save()\` \u2014 it's async
- \u2717 \`new TextRun("text", { bold: true })\` \u2014 wrong! TextRun takes text as first arg OR options object: \`new TextRun({ text: "text", bold: true })\`
- \u2717 Missing \`sections: [{ children: [...] }]\` \u2014 Document requires at least one section
- \u2717 Using \`document.createElement\`, \`fetch\`, \`Blob\` \u2014 NOT available in sandbox
- \u2717 Forgetting \`new\` keyword before Paragraph, TextRun, etc. \u2014 these are constructors

### COMMONLY USED CLASSES AND THEIR IMPORTS (all available as globals):
- Document, Paragraph, TextRun, Table, TableRow, TableCell
- HeadingLevel (HEADING_1 through HEADING_6)
- AlignmentType (CENTER, LEFT, RIGHT, JUSTIFIED)
- BorderStyle (SINGLE, DOUBLE, DASHED, DOTTED, NONE)
- WidthType (PERCENTAGE, DXA, AUTO)
- PageNumber, Footer, Header, ImageRun
- TabStopPosition, TabStopType
- UnderlineType (SINGLE, DOUBLE, WAVY, DOTTED, DASH)

### TEXT STYLING OPTIONS (inside TextRun):
{ text: string, bold?: boolean, italics?: boolean, size?: number (half-points, e.g. 24 = 12pt),
  color?: string (hex), font?: string, underline?: { type: UnderlineType, color?: string },
  strike?: boolean, superScript?: boolean, subScript?: boolean }

### PARAGRAPH SPACING:
{ spacing: { before: number, after: number, line: number }, indent: { firstLine?: number, left?: number } }
`.trim(),D=[{name:"xlsx",keywords:["excel","spreadsheet","xlsx","xls","sheet","tabular data","workbook","cells",".xlsx"],skill:H},{name:"pptx",keywords:["powerpoint","presentation","slide","pptx",".pptx","slideshow","deck","power point"],skill:J},{name:"docx",keywords:["word","document","docx","msword","word document","doc",".docx","letter","report"],skill:G}];function z(e){if(!e||typeof e!="string")return[];const t=e.toLowerCase(),n=[];for(const r of D)for(const i of r.keywords)if(t.includes(i)){n.push(r.name);break}return n}function W(e){const t=z(e);if(!t.length)return"";const n=[];for(const r of t){const i=D.find(c=>c.name===r);i&&n.push(i.skill)}return n.length?["<BetterDeepSeek>","[OFFICE SKILL] The user wants to create an office document. Below is the API reference for the required library:","",n.join(`

`),"</BetterDeepSeek>"].join(`
`):""}const Y=new Set(["the","a","an","and","or","but","if","then","else","when","at","by","for","with","about","against","is","it","was","were","are","be","been","between","into","through","during","before","after","above","below","to","from","up","down","in","out","on","off","over","under","again","further","once","here","there","all","any","both","each","few","more","most","other","some","such","no","nor","not","only","own","same","so","than","too","very","can","will","just","should","now","how","what","where","why","who","which","ve","veya","ama","fakat","lakin","ancak","ise","ki","de","da","mi","mu","m\xFC","m\u0131","bir","bu","\u015Fu","o","i\xE7in","gibi","kadar","ile","taraf\u0131ndan","hakk\u0131nda","kar\u015F\u0131","aras\u0131nda","i\xE7ine","boyunca","\xF6nce","sonra","\xFCzerinde","alt\u0131nda","yine","daha","en","t\xFCm","her","baz\u0131","hi\xE7","sadece","kendi","ayn\u0131","\xF6yle","b\xF6yle","\xE7ok","yap\u0131lan","yaparak","olan"]);function V(e,t=800,n=5){if(!e||!e.content)return[];const r=e.content.split(/\r?\n/);if(r.length===0)return[];const i=[];let c=0;for(;c<r.length;){const u=[];let s=0;const f=c+1;for(;c<r.length&&(s<t||u.length<3);)u.push(r[c]),s+=r[c].length+1,c++;const l=c;if(i.push({fileName:e.name,content:u.join(`
`),startLine:f,endLine:l}),c>=r.length)break;c=Math.max(f,c-n)}return i}function N(e){return e?(String(e).toLowerCase().match(/[a-z0-9_\u015f\u00e7g\u00f6\u0131\u00fc]+/gi)||[]).filter(n=>n.length>=2&&!Y.has(n)):[]}function K(e,t,n=5){if(!e||!t||!t.length)return[];const r=[];for(const S of t)r.push(...V(S,800,5));if(r.length===0)return[];const i=N(e);if(i.length===0)return[];const c=r.length,u=r.map(S=>N(S.content)),s=u.map(S=>S.length),l=s.reduce((S,k)=>S+k,0)/c||1,d={};for(const S of i){d[S]=0;for(const k of u)k.includes(S)&&d[S]++}const h=1.2,y=.75,x=[];for(let S=0;S<c;S++){const k=r[S],g=u[S],w=s[S];let o=0;const a={};for(const m of g)a[m]=(a[m]||0)+1;for(const m of i){const b=a[m]||0;if(b===0)continue;const T=d[m]||0,L=Math.log(1+(c-T+.5)/(T+.5))*(b*(h+1))/(b+h*(1-y+y*(w/l)));o+=L}const p=String(k.fileName).toLowerCase();for(const m of i)p.includes(m)&&(o+=12);o>0&&x.push({...k,score:o})}return x.sort((S,k)=>k.score-S.score).slice(0,Math.max(1,n))}function Q(e,t="Project"){if(!e||!e.length)return"";let n=`<BDS:PROJECT_CONTEXT>
`;n+=`You are working on the project "${t}". Based on the user's latest prompt, here are the most relevant sections of the project files:

`;for(const r of e){const i=r.fileName.split(".").pop()||"";n+=`--- [FILE: ${r.fileName} (Lines ${r.startLine}-${r.endLine})] ---
`,n+=`\`\`\`${i}
`,n+=r.content+`
`,n+="```\n\n"}return n+="</BDS:PROJECT_CONTEXT>",n}function O(e,t){var x,S,k;t.sessionUserMsgCounts||(t.sessionUserMsgCounts={});const n=Z(e),r=ee(e);let i=1;n&&n.length>0?(i=n.filter(g=>{const w=String(g.role||g.author||"").toLowerCase();return w==="user"||w==="human"}).length,t.sessionUserMsgCounts[r]=i):typeof e.prompt=="string"&&(e.message_id===1||e.parent_message_id==null?i=1:i=(t.sessionUserMsgCounts[r]||0)+1,t.sessionUserMsgCounts[r]=i);let c=!1,u=null;if(n&&n.length>0){u=v(n)||n[n.length-1];const g=C(u);if(g){const w=B(g),o=te(n,u);let a=!1;const p=t.config.systemPromptInjectionFrequency||"first";if(p==="always")a=!0;else if(p==="every_x"){const b=t.config.systemPromptInjectionInterval||3;(i-1)%b===0?a=!0:o||(a=!0)}else a=!o,(n.length>1||t.hasInjected&&t.hasInjected(r))&&(a=!1);const m=I(w,r,t,a,n,u);window.dispatchEvent(new CustomEvent("bds:mutation-applied",{detail:JSON.stringify({conversationId:r,injectedText:m||"",userPrompt:w})})),m?(A(u,`${m}

${w}`),c=!0):w!==g&&(A(u,w),c=!0)}}else if(typeof e.prompt=="string"){const g=B(e.prompt),w=e.message_id===1||e.parent_message_id==null,o=t.config.systemPromptInjectionFrequency||"first";let a=!1;if(o==="always")a=!0;else if(o==="every_x"){const m=t.config.systemPromptInjectionInterval||3;(w||(i-1)%m===0)&&(a=!0)}else a=w;const p=I(g,r,t,a,null,null);window.dispatchEvent(new CustomEvent("bds:mutation-applied",{detail:JSON.stringify({conversationId:r,injectedText:p||"",userPrompt:g})})),p?(e.prompt=`${p}

${g}`,c=!0):g!==e.prompt&&(e.prompt=g,c=!0)}const s=(x=t.config)==null?void 0:x.modelInputLimits,f=e.model||((S=e.data)==null?void 0:S.model)||((k=e.chat)==null?void 0:k.model)||"",l=String(f).toLowerCase();let d="instant",h="payload";if(l)l.includes("vision")?d="vision":l.includes("reasoner")||l.includes("deepthink")||l.includes("r1")?d="deepthink":(l.includes("expert")||l.includes("pro"))&&(d="expert");else{const g=be();g&&(d=g,h="dom")}const y=s?s[d]??163840:163840;if(n&&n.length>0){const g=v(n);if(g){const w=C(g);if(console.warn(`[BDS] Guard check: model="${l}" payload.model=${e.model} source=${h} type=${d} limit=${y} msgLen=${w.length} limits=${JSON.stringify(s)}`),w.length>y){const o=`

...[truncated by Better DeepSeek]...`,a=w.slice(0,y-o.length)+o;A(g,a),c=!0,console.warn(`[BDS] TRUNCATED user message from ${w.length} to ${y} chars`)}}}else if(typeof e.prompt=="string"&&(console.warn(`[BDS] Guard check (prompt): model="${l}" payload.model=${e.model} source=${h} type=${d} limit=${y} msgLen=${e.prompt.length} limits=${JSON.stringify(s)}`),e.prompt.length>y)){const g=`

...[truncated by Better DeepSeek]...`;e.prompt=e.prompt.slice(0,y-g.length)+g,c=!0,console.warn(`[BDS] TRUNCATED prompt from ${e.prompt.length} to ${y} chars`)}return{changed:c,payload:e}}function Z(e){return Array.isArray(e.messages)?e.messages:e.data&&Array.isArray(e.data.messages)?e.data.messages:e.chat&&Array.isArray(e.chat.messages)?e.chat.messages:null}function ee(e){return String(e.conversation_id||e.conversationId||e.chat_session_id||e.chat_id||e.id||"default")}function v(e){for(let t=e.length-1;t>=0;t-=1){const n=e[t];if(!n||typeof n!="object")continue;const r=String(n.role||n.author||"").toLowerCase();if(r==="user"||r==="human")return n}return null}function C(e){return e?typeof e.content=="string"?e.content:Array.isArray(e.content)?e.content.map(t=>typeof t=="string"?t:t&&typeof t.text=="string"?t.text:"").join(`
`):typeof e.prompt=="string"?e.prompt:"":""}function A(e,t){if(e){if(typeof e.content=="string"||e.content==null){e.content=t;return}if(Array.isArray(e.content)){e.content=[{type:"text",text:t}];return}if(typeof e.prompt=="string"){e.prompt=t;return}e.content=t}}function te(e,t=null){if(!Array.isArray(e))return!1;for(const n of e){if(n===t)continue;if(C(n).includes("<BetterDeepSeek>"))return!0}return!1}function I(e,t,n,r=!1,i=null,c=null){var w;const u=[],s=ne(e,t,n);s&&u.push(s);const f=n.config.systemPromptEntries||[];if(f.length>0){const o=n.sessionUserMsgCounts[t]||1;for(const a of f)a.content.trim()&&me(a,o,t,n)&&(u.push(`<BetterDeepSeek>
${a.content.trim()}
</BetterDeepSeek>`),n.markEntryInjected&&n.markEntryInjected(t,a.id))}else r&&n.config.systemPrompt.trim()&&!n.config.disableSystemPrompt&&(u.push(`<BetterDeepSeek>
${n.config.systemPrompt.trim()}
</BetterDeepSeek>`),n.markInjected&&n.markInjected(t));const l=_(n.config.skills);let d=null;if(!r&&i&&(d=Se(i,c)),r||l&&l!==d){const o=oe(n);o&&u.push(o)}const h=le(e,n,i);h&&u.push(h);const y=W(e);y&&u.push(y);const x=n.config.activeCharacter;if(x){let o=i?ge(i,c):null;if(!o&&n.getLastChar&&(o=n.getLastChar(t)),!o&&n.currentSessionChar&&(i==null?void 0:i.length)>1&&(o=n.currentSessionChar),r||!o||o!==x.name){const a=pe(n);a&&(u.push(a),n.setLastChar&&n.setLastChar(t,x.name),n.currentSessionChar=x.name)}}n.isNextVoiceMessage&&(u.push("<BetterDeepSeek>User send this message using voice recorder tool.</BetterDeepSeek>"),n.isNextVoiceMessage=!1);const S=n.config&&n.config.activeProject;if(S){let o=null;if(!r&&i&&(o=ye(i,c)),r||!o||o!==S.name){const a=de(n);a&&u.push(a)}if(n.config.projectRagEnabled&&Array.isArray(S.files)&&S.files.length>0){const a=Number(n.config.projectRagLimit)||5,p=K(e,S.files,a);if(p&&p.length>0){const m=Q(p,S.name);m&&u.push(m)}}}if(r){const o=fe(n);o&&u.push(o)}const k=ie((w=n.config)==null?void 0:w.mcpToolSchemas);let g=null;if(!r&&i&&(g=we(i,c)),r||k&&k!==g){const o=he(n,k);o&&u.push(o)}return u.join(`

`)}function ne(e,t,n){var i;const r=(i=n.config)==null?void 0:i.deepResearch;return!(r!=null&&r.enabled)||!r.runId?"":(r.enabled=!1,re(r.runId,t,e),["<BetterDeepSeek>",'[BDS:DEEP_RESEARCH] The DeepResearch toggle is enabled. Treat this exactly as the user asking: "Perform Deep Research on the following request."',`Run ID: ${r.runId}`,"","CRITICAL: In this first turn, you must ONLY produce a research plan. Do NOT browse or search. Do NOT produce an ordinary answer. Do NOT produce a direct report.",`Output ONLY a plan using: <BDS:DEEP_RESEARCH_PLAN runId="${r.runId}">JSON</BDS:DEEP_RESEARCH_PLAN>`,"After this turn, BDS will execute steps one-by-one. After each step result is provided, analyze it before continuing. Do NOT skip ahead to the final report until BDS tells you all steps are complete.","","The JSON plan must include:",'- "title": A short descriptive title for the research','- "steps": An array of research steps, each with:','  - "id": step number','  - "action": "search" or "fetch"','  - "query": a specific search query or URL to fetch','  - "purpose": why this step is needed','  - "sourceType": for search steps, one of "general", "docs", "news", "reviews", "academic", or "commerce"',"","Search steps must use narrow queries with named entities, constraints, dates or locations, product or version names, and clear source intent.","",`User research question: ${e}`,"</BetterDeepSeek>"].join(`
`))}function re(e,t,n){typeof window>"u"||!window.dispatchEvent||window.dispatchEvent(new CustomEvent("bds:deep-research-started",{detail:JSON.stringify({runId:e,conversationId:t,userPrompt:n,timestamp:Date.now()})}))}function oe(e){if(!e.config.skills.length)return"";const t=e.config.skills.map(n=>`## ${n.name}
${n.content.trim()}`).join(`

`);return`<BetterDeepSeek> <BDS:SKILLS fingerprint="${_(e.config.skills)}">
${t}
</BDS:SKILLS> </BetterDeepSeek>`}function _(e){return!Array.isArray(e)||!e.length?"":e.map(t=>`${t.name}:${(t.content||"").length}`).sort().join("|")}function ie(e){return!Array.isArray(e)||!e.length?"":e.map(t=>`${t.serverName}:${t.toolName}:${JSON.stringify(t.inputSchema||{})}`).sort().join("|")}function se(e){if(!Array.isArray(e))return null;for(let t=e.length-1;t>=0;t--){const n=e[t];if(!n||typeof n!="object")continue;const r=String(n.role||n.author||"").toLowerCase();if(!(r==="user"||r==="human")&&(r==="assistant"||r==="ai"||r==="bot"))return n}return null}function P(e){return!e||typeof e!="string"?[]:e.split(new RegExp("[_-]|\\s+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")).map(t=>t.toLowerCase().replace(/[^a-z0-9]/g,"")).filter(t=>t.length>0)}function ae(e,t){if(!e.length||!t.length)return 0;const n=new Set(t);let r=0;for(const i of e)n.has(i)&&r++;return r/e.length}function ce(e,t){return t===1?e>=1:e>=.5}function le(e,t,n){if(t.config.disableMemory||!t.config.memories.length)return"";const r=n?se(n):null,i=r?C(r):"",c=[e,i].filter(Boolean).join(" "),u=P(c),s=[];for(const l of t.config.memories){if(l.importance==="always"){s.push(l);continue}if(!l.key)continue;const d=P(l.key);if(!d.length){c.toLowerCase().includes(l.key.toLowerCase())&&s.push(l);continue}const h=[...new Set(d)],y=ae(h,u);(ce(y,h.length)||c.toLowerCase().includes(l.key.toLowerCase()))&&s.push(l)}return s.length?`<BetterDeepSeek>
${s.map(l=>`<BDS:memory_calls importance="${l.importance}">${l.key}: ${ue(l.value)}</BDS:memory_calls>`).join(`
`)}
</BetterDeepSeek>`:""}function ue(e){return String(e).replace(/<\//g,"<\\/").trim()}function de(e){const t=e.config&&e.config.activeProject;if(!t)return"";let n="";return t.instructions&&t.instructions.trim()&&(n+=t.instructions.trim()+`
`),`<BetterDeepSeek>
<BDS:PROJECT name="${t.name}">
${n}</BDS:PROJECT>
</BetterDeepSeek>`}function pe(e){const t=e.config.activeCharacter;if(!t||!t.content)return"";let n=`Character Name: ${t.name}
`;return t.usage&&(n+=`Usage Domain: ${t.usage}
`),n+=`---
${t.content.trim()}`,`<BetterDeepSeek> <BDS:RP>
${n}
</BDS:RP> </BetterDeepSeek>`}function fe(e){const t=[];if(e.config.injectSystemDateTime!==!1){const r=new Date;t.push(`User's System Date & Time: ${r.toLocaleString()}`)}const n=e.config.preferredLang;return n&&n.trim()&&t.push(`Always respond in ${n.trim()}.`),t.length===0?"":`<BetterDeepSeek>
${t.join(`
`)}
</BetterDeepSeek>`}function he(e,t){var w;const n=(w=e.config)==null?void 0:w.mcpToolSchemas;if(!Array.isArray(n)||!n.length)return"";const r=Number(e.config.mcpInlineMaxChars)||8e3,i=n.length,c=[`<BetterDeepSeek> <BDS:MCP fingerprint="${t}">`,"You have access to the following MCP (Model Context Protocol) tools via remote servers.",`To invoke them, use: <BDS:AUTO:MCP url="SERVER_NAME_OR_URL" tool="TOOL_NAME" args='{"key":"value"}'>`,"The extension will call the tool and inject the result.","Important: Only ONE tool per response. Wait for the result before invoking another. Never invoke multiple tools at the same time.","","Available tools:"].join(`
`),u="</BDS:MCP> </BetterDeepSeek>",s=n.map(o=>{let a=`- Server: ${o.serverName} (${o.serverUrl||o.serverName}) | Tool: ${o.toolName}`;if(o.description&&(a+=` | Description: ${o.description}`),o.inputSchema&&typeof o.inputSchema=="object"){const p=o.inputSchema.properties;if(p){const m=Object.entries(p).map(([b,T])=>{const E=(o.inputSchema.required||[]).includes(b)?" (required)":"";return`${b}: ${(T==null?void 0:T.type)||"any"}${E}`});m.length&&(a+=` | Params: ${m.join(", ")}`)}}return a}),f=[c,...s,u].join(`
`);if(f.length<=r)return f;const l=o=>`
... and ${o} more tool(s) not shown (MCP tool list exceeds inline character limit \u2014 all tools are still available for invocation).`,d=l(1),h=c.length+1+u.length+d.length;let y=r-h;const x=[];for(const o of s){const a=o.length+1;if(y-a<0)break;y-=a,x.push(o)}const S=i-x.length,k=l(S);let g=[c,...x,k,u].join(`
`);for(;x.length>0&&g.length>r;){x.pop();const o=i-x.length,a=l(o);g=[c,...x,a,u].join(`
`)}return g}function me(e,t,n,r){const c=(r.getInjectedEntries?r.getInjectedEntries(n):[]).includes(e.id);switch(e.schedule.type){case"first":return!c;case"always":return!0;case"interval":{const u=e.schedule.everyNTurns||3;return c?(t-1)%u===0:!0}default:return!1}}function ge(e,t=null){if(!Array.isArray(e))return null;for(let n=e.length-1;n>=0;n--){const r=e[n];if(r===t)continue;const i=C(r);if(!i.includes("<BDS:RP>"))continue;const c=i.match(/Character Name:\s*(.*?)\n/);if(c&&c[1])return c[1].trim()}return null}function Se(e,t=null){if(!Array.isArray(e))return null;for(let n=e.length-1;n>=0;n--){const r=e[n];if(r===t)continue;const c=C(r).match(/<BDS:SKILLS fingerprint="(.*?)">/);if(c&&c[1])return c[1]}return null}function we(e,t=null){if(!Array.isArray(e))return null;for(let n=e.length-1;n>=0;n--){const r=e[n];if(r===t)continue;const c=C(r).match(/<BDS:MCP fingerprint="(.*?)">/);if(c&&c[1])return c[1]}return null}function ye(e,t=null){if(!Array.isArray(e))return null;for(let n=e.length-1;n>=0;n--){const r=e[n];if(r===t)continue;const c=C(r).match(/<BDS:PROJECT name="(.*?)">/);if(c&&c[1])return c[1]}return null}function B(e){let t=String(e||"");return t=t.replace(/<BetterDeepSeek>([\s\S]*?)<\/BetterDeepSeek>/gi,(n,r)=>r.includes("[BDS:AUTO]")||r.includes("[BDS:DEEP_RESEARCH]")||/<BDS:memory_calls[\s>]/i.test(r)?n:""),t=t.replace(/<BDS:SKILLS>[\s\S]*?<\/BDS:SKILLS>/gi,""),t=t.replace(/<BDS:memory_calls[^>]*>[\s\S]*?<\/BDS:memory_calls>/gi,""),t=t.replace(/<BDS:RP>[\s\S]*?<\/BDS:RP>/gi,""),t=t.replace(/<BDS:PROJECT[^>]*>[\s\S]*?<\/BDS:PROJECT>/gi,""),t=t.replace(/<BDS:PROJECT_CONTEXT>[\s\S]*?<\/BDS:PROJECT_CONTEXT>/gi,""),t.trim()}function be(){try{const e=document.querySelector("._46a12ab");if(!e)return null;const t=(e.textContent||"").toLowerCase().trim();return t.includes("vision")?"vision":t.includes("expert")||t.includes("reasoner")?"expert":t.includes("deepthink")||t.includes("deep think")||t.includes("r1")?"deepthink":t.includes("instant")||t.includes("chat")||t.includes("flash")?"instant":null}catch{return null}}function Te(e,t,n,r){const i=window.fetch;window.fetch=async function(u,s){try{const f=xe(u);if(!t(f))return i.apply(this,arguments);if(Ae(u,s,e),f.includes("/api/v0/chat_session/fetch_page")){const l=await i.apply(this,arguments);return l.clone().json().then(h=>{window.dispatchEvent(new CustomEvent("bds:session-data",{detail:JSON.stringify(h)}))}).catch(()=>{}),l}if(f.includes("/api/v0/chat/history_messages")){const l=await i.apply(this,arguments);return l.clone().json().then(h=>{window.dispatchEvent(new CustomEvent("bds:history-msgs",{detail:JSON.stringify(h)}))}).catch(()=>{}),l}n(f);try{const l=await ke(u,s,e);if(!l){const h=await i.apply(this,arguments);return j(h,f,l==null?void 0:l.modelName),h}const d=await i.call(this,l.input,l.init);return d&&d.status>=500&&window.dispatchEvent(new CustomEvent("bds:network-error",{detail:JSON.stringify({url:f,status:d.status,type:"fetch"})})),j(d,f,l.modelName),d}catch(l){throw window.dispatchEvent(new CustomEvent("bds:network-error",{detail:JSON.stringify({url:f,status:0,type:"fetch",error:String(l)})})),l}finally{r(f)}}catch(f){return console.warn("[BetterDeepSeek] Request patch failed:",f),i.apply(this,arguments)}}}function j(e,t,n){if(!(!e||!e.clone))try{const r=e.clone();Ee(r,n).catch(()=>{})}catch{}}function xe(e){return typeof e=="string"?e:e instanceof URL?e.toString():e instanceof Request?e.url:""}async function ke(e,t,n){const r=await Le(e,t);if(!r)return null;let i;try{i=JSON.parse(r)}catch{return null}const c=i.model||null,u=O(i,n);if(!u.changed)return null;const s=JSON.stringify(u.payload),f=t&&t.headers?t.headers:e instanceof Request?e.headers:void 0,l=new Headers(f||{});l.set("content-type","application/json");const d={method:t&&t.method||(e instanceof Request?e.method:"POST"),headers:l,body:s,credentials:t&&t.credentials||(e instanceof Request?e.credentials:void 0),cache:t&&t.cache||(e instanceof Request?e.cache:void 0),mode:t&&t.mode||(e instanceof Request?e.mode:void 0),redirect:t&&t.redirect||(e instanceof Request?e.redirect:void 0),referrer:t&&t.referrer||(e instanceof Request?e.referrer:void 0),referrerPolicy:t&&t.referrerPolicy||(e instanceof Request?e.referrerPolicy:void 0),keepalive:t&&t.keepalive||(e instanceof Request?e.keepalive:void 0),integrity:t&&t.integrity||(e instanceof Request?e.integrity:void 0),signal:t&&t.signal||(e instanceof Request?e.signal:void 0)};return{input:typeof e=="string"||e instanceof URL?e:e.url,init:d,modelName:c}}async function Ee(e,t){try{const n=e.headers.get("content-type")||"";if(n.includes("text/event-stream")||n.includes("stream"))await Ce(e,t);else{const r=await e.text();try{const i=JSON.parse(r),c=(i==null?void 0:i.usage)||(i==null?void 0:i.token_usage);c&&M(c.prompt_tokens||c.input_tokens||0,c.completion_tokens||c.output_tokens||0,t)}catch{}}}catch{}}async function Ce(e,t){var u;const n=(u=e.body)==null?void 0:u.getReader();if(!n)return;const r=new TextDecoder;let i="";try{for(;;){const{done:s,value:f}=await n.read();if(f&&(i+=r.decode(f,{stream:!s})),s)break}}catch{return}const c=i.split(`
`);for(let s=c.length-1;s>=0;s--){const f=c[s].trim();if(!f.startsWith("data: "))continue;const l=f.slice(6).trim();if(l!=="[DONE]")try{const d=JSON.parse(l),h=(d==null?void 0:d.usage)||(d==null?void 0:d.token_usage);if(h){M(h.prompt_tokens||h.input_tokens||0,h.completion_tokens||h.output_tokens||0,t||(d==null?void 0:d.model));break}}catch{}}}function M(e,t,n){typeof e!="number"&&typeof t!="number"||window.dispatchEvent(new CustomEvent("bds:token-usage",{detail:JSON.stringify({inputTokens:Number(e)||0,outputTokens:Number(t)||0,modelName:n||null,timestamp:Date.now()})}))}async function Le(e,t){return t&&typeof t.body=="string"?t.body:t&&t.body instanceof URLSearchParams?t.body.toString():e instanceof Request?e.clone().text():""}function Ae(e,t,n){try{let r;if(t&&t.headers){const i=t.headers;if(i instanceof Headers)r=i.get("authorization");else if(Array.isArray(i)){for(const[c,u]of i)if(c.toLowerCase()==="authorization"){r=u;break}}else typeof i=="object"&&(r=i.Authorization||i.authorization)}!r&&e instanceof Request&&(r=e.headers.get("authorization")),r&&typeof(n==null?void 0:n.setAuthToken)=="function"&&n.setAuthToken(r)}catch{}}function Re(e,t,n,r){const i=XMLHttpRequest.prototype.open,c=XMLHttpRequest.prototype.send,u=XMLHttpRequest.prototype.setRequestHeader;XMLHttpRequest.prototype.open=function(f,l){return this.__bdsRequestMeta={method:String(f||"GET").toUpperCase(),url:String(l||"")},i.apply(this,arguments)},XMLHttpRequest.prototype.setRequestHeader=function(f,l){return f&&String(f).toLowerCase()==="authorization"&&typeof(e==null?void 0:e.setAuthToken)=="function"&&e.setAuthToken(String(l||"")),u.apply(this,arguments)},XMLHttpRequest.prototype.send=function(f){try{const l=this.__bdsRequestMeta||{};if(!t(l.url))return c.call(this,f);if(l.url.includes("/api/v0/chat_session/fetch_page"))return this.addEventListener("load",()=>{try{const o=JSON.parse(this.responseText);window.dispatchEvent(new CustomEvent("bds:session-data",{detail:JSON.stringify(o)}))}catch{}}),c.call(this,f);if(l.url.includes("/api/v0/chat/history_messages"))return this.addEventListener("load",()=>{try{const o=JSON.parse(this.responseText);window.dispatchEvent(new CustomEvent("bds:history-msgs",{detail:JSON.stringify(o)}))}catch{}}),c.call(this,f);n(l.url);let d=!1;const h=()=>{d||(d=!0,(this.status>=500||this.status===0)&&window.dispatchEvent(new CustomEvent("bds:network-error",{detail:JSON.stringify({url:l.url,status:this.status,type:"xhr"})})),r(l.url))};this.addEventListener("loadend",h,{once:!0});const y=De(f);if(!y)return c.call(this,f);const x=JSON.parse(y),S=x.model||null,k=O(x,e);if(!k.changed)return c.call(this,f);const g=JSON.stringify(k.payload),w=this;return this.addEventListener("load",()=>{try{const o=w.responseText;o&&Ne(o,w,S)}catch{}},{once:!0}),c.call(this,g)}catch(l){const d=this.__bdsRequestMeta||{};console.warn("[BetterDeepSeek] XHR patch failed:",l);try{return c.call(this,f)}catch(h){throw t(d.url)&&r(d.url),h}}}}function De(e){return typeof e=="string"?e:e instanceof URLSearchParams?e.toString():""}function Ne(e,t,n){var r;try{if((((r=t.getResponseHeader)==null?void 0:r.call(t,"content-type"))||"").includes("text/event-stream")||e.startsWith("data: ")){const c=e.split(`
`);for(let u=c.length-1;u>=0;u--){const s=c[u].trim();if(!s.startsWith("data: "))continue;const f=s.slice(6).trim();if(f!=="[DONE]")try{const l=JSON.parse(f),d=l==null?void 0:l.usage;if(d){window.dispatchEvent(new CustomEvent("bds:token-usage",{detail:JSON.stringify({inputTokens:d.prompt_tokens||d.input_tokens||0,outputTokens:d.completion_tokens||d.output_tokens||0,modelName:n||(l==null?void 0:l.model)||null,timestamp:Date.now()})}));break}}catch{}}}}catch{}}(function(){"use strict";const e={configUpdate:"bds:config-update",deepResearchConfigUpdate:"bds:deep-research-config-update",requestConfig:"bds:request-config",markVoiceMessage:"bds:mark-voice-message",sessionData:"bds:session-data"},t="/api/v0/chat_session/fetch_page",n="/api/v0/chat/history_messages",r="/api/v0/chat/completion";function i(){try{return JSON.parse(localStorage.getItem("bds_injected_chats")||"[]")}catch{return[]}}function c(o){const a=i();a.includes(o)||(a.push(o),a.length>50&&a.shift(),localStorage.setItem("bds_injected_chats",JSON.stringify(a)))}function u(){try{return JSON.parse(localStorage.getItem("bds_injected_chars")||"{}")}catch{return{}}}function s(o,a){const p=u();p[o]=a;const m=Object.keys(p);m.length>50&&delete p[m[0]],localStorage.setItem("bds_injected_chars",JSON.stringify(p))}function f(o){try{return JSON.parse(localStorage.getItem("bds_injected_entries")||"{}")[o]||[]}catch{return[]}}function l(o,a){try{const p=JSON.parse(localStorage.getItem("bds_injected_entries")||"{}");p[o]||(p[o]=[]),p[o].includes(a)||p[o].push(a);const m=Object.keys(p);m.length>50&&delete p[m[0]],localStorage.setItem("bds_injected_entries",JSON.stringify(p))}catch{}}function d(){var o,a;try{for(let m=0;m<localStorage.length;m++){const b=localStorage.key(m);if(b&&/token|auth|session/i.test(b)){const T=localStorage.getItem(b);if(!T)continue;if(T.trim().startsWith("{"))try{const E=JSON.parse(T),L=E.token||E.accessToken||E.access_token||E.user_token||((o=E.user)==null?void 0:o.token);if(L&&typeof L=="string")return L}catch{}else if(typeof T=="string"&&T.length>20){let E=T;return E.startsWith("Bearer ")&&(E=E.substring(7)),E.startsWith('"')&&E.endsWith('"')&&(E=E.slice(1,-1)),E}}}const p=(a=document.cookie.split("; ").find(m=>m.startsWith("user_token=")||m.startsWith("token=")))==null?void 0:a.split("=")[1];if(p)return decodeURIComponent(p)}catch(p){console.warn("[BDS] Failed to search auth token in storage:",p)}return null}const h={config:{systemPrompt:"",systemPromptEntries:[],skills:[],memories:[],activeCharacter:null,mcpToolSchemas:[]},hasInjected:o=>i().includes(o),markInjected:o=>c(o),getInjectedEntries:o=>f(o),markEntryInjected:(o,a)=>l(o,a),getLastChar:o=>u()[o]||null,setLastChar:(o,a)=>s(o,a),currentSessionChar:null,activeCompletionRequests:0,isNextVoiceMessage:!1,authToken:d(),setAuthToken:function(o){o&&o!==this.authToken&&(this.authToken=o)}};if(window.__bdsNetworkPatched)return;window.__bdsNetworkPatched=!0,(function(){if(window.__BDS_CONFIG__)return;let o=0;const a=new Map;window.addEventListener("bds:debug-api-response",m=>{let b=m.detail;if(typeof b=="string")try{b=JSON.parse(b)}catch{return}const T=a.get(b.id);T&&(T(b.result),a.delete(b.id))});function p(m){return function(){const b=Array.from(arguments);return new Promise(T=>{const E=++o;a.set(E,T),window.dispatchEvent(new CustomEvent("bds:debug-api-request",{detail:JSON.stringify({id:E,method:m,args:b})}))})}}window.__BDS_CONFIG__={raw:p("getRaw"),getFlag:p("getFlag"),getConfig:p("getConfig"),applyRemote:p("applyRemote"),replaceRemote:p("replaceRemote"),resetToBuiltin:p("resetToBuiltin"),detectModel:p("detectModel"),toggleDebugPanel:p("toggleDebugPanel")}})(),window.addEventListener(e.configUpdate,o=>{let a=o&&o.detail?o.detail:{};if(typeof a=="string")try{a=JSON.parse(a)}catch(p){console.error("[BDS] Failed to parse configUpdate detail:",p)}h.config=X(a||{})}),window.addEventListener(e.deepResearchConfigUpdate,o=>{let a=o&&o.detail?o.detail:{};if(typeof a=="string")try{a=JSON.parse(a)}catch(p){console.error("[BDS] Failed to parse deepResearchConfigUpdate detail:",p)}h.config.deepResearch=R(a||{})}),window.addEventListener(e.markVoiceMessage,()=>{h.isNextVoiceMessage=!0}),window.addEventListener("bds:request-history-msgs",async o=>{let a=o&&o.detail?o.detail:{};if(typeof a=="string")try{a=JSON.parse(a)}catch{return}const p=a==null?void 0:a.sessionId;if(!p)return;const m=`${n}?chat_session_id=${encodeURIComponent(p)}`,b={"Content-Type":"application/json"};h.authToken&&(b.Authorization=`Bearer ${h.authToken}`);try{const T=await y(m,{method:"GET",headers:b,credentials:"include"});if(!T.ok){console.warn("[BDS] history_mgs fetch failed:",T.status);return}const E=await T.json();E.__bdsExplicit=!0,window.dispatchEvent(new CustomEvent("bds:history-msgs",{detail:JSON.stringify(E)}))}catch(T){console.warn("[BDS] history_msgs fetch error:",T)}}),x();const y=window.fetch.bind(window);Te(h,S,g,w),Re(h,S,g,w);function x(){window.dispatchEvent(new CustomEvent(e.requestConfig))}function S(o){const a=String(o||"");return a.includes("/api/v0/chat/completion")||a.includes("/api/v0/chat/edit_message")||a.includes(t)||a.includes(n)}function k(o,a){const p={status:o,url:String(a||""),activeCompletionRequests:h.activeCompletionRequests,timestamp:Date.now()};window.dispatchEvent(new CustomEvent(e.networkState,{detail:JSON.stringify(p)}))}function g(o){h.activeCompletionRequests+=1,k("start",o)}function w(o){h.activeCompletionRequests=Math.max(0,h.activeCompletionRequests-1),k("end",o)}})()})();
