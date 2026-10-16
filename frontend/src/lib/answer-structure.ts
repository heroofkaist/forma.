export type AnswerSection={latex?:string;interpretation?:string;id:string;page_number:number;kind:string;transcription:string;question_id:string|null;criterion_ids?:string[];readability:string;rationale:string;uncertainty_notes:string[];evidence_kind:string};
export type AnswerQuestion={id:string;title:string;maximum_points?:number;criteria?:{criterion_id?:string;id?:string;description:string;maximum_points:number}[]};
export type AnswerGroup={id:string;question_id:string;title:string;mode?:string;criterion_ids:string[];criteria:NonNullable<AnswerQuestion['criteria']>;maximum_points?:number};
export function groupSections(sections:AnswerSection[],groups:AnswerGroup[]){
 const assigned=new Set<string>();
 const rows=groups.map(group=>{const items=sections.filter(s=>s.question_id===group.question_id&&(group.mode!=='problem_criteria'||s.criterion_ids?.some(id=>group.criterion_ids.includes(id))));items.forEach(s=>assigned.add(s.id));return{group,sections:items};});
 return {rows,unassigned:sections.filter(s=>!assigned.has(s.id))};
}
export function readableStatus(value:string){return ({readable:'Текст распознан',uncertain:'Нужно сверить с оригиналом',unreadable:'Не удалось прочитать',missing:'Текст не найден'} as Record<string,string>)[value]??'Нужно сверить с оригиналом';}
export function analysisWarning(text:string){
 if(/Gemini is not configured/i.test(text))return 'Распознавание изображений не настроено. Доступен только текст, встроенный в файл; рукописные ответы нужно проверить по оригиналу.';
 const page=/Page (\d+): no embedded text/i.exec(text);
 if(page)return `На странице ${page[1]} нет встроенного текста. Для скана или рукописи проверьте результат распознавания и оригинал.`;
 if(/DOCX page numbers/i.test(text))return 'В DOCX нельзя точно восстановить страницы и исходное оформление. Привязка идёт по абзацам и таблицам.';
 if(/PPTX text and tables/i.test(text))return 'Из презентации извлечены текст и таблицы. Устное выступление и подача по файлу не оцениваются.';
 if(/Source files.*static review/i.test(text))return 'Код проверяется по содержимому. Программа не запускается, результаты выполнения не подтверждены.';
 if(/Long assignment instructions/i.test(text))return 'В запрос вошли не все условия задания. Сверьте привязку ответов с полным условием.';
 if(/Visual page budget/i.test(text))return 'Обработаны не все сканы: достигнут лимит страниц. Остальные страницы нужно проверить вручную.';
 if(/Provider-proposed|Qwen output is unverified|AI interpretation requires/i.test(text))return 'Распознанный текст и пояснения ИИ нужно сверить с оригиналом.';
 if(/Question context is bounded/i.test(text))return 'Проверьте привязку ответов к условиям и критериям задания.';
 if(/PARTIAL ANALYSIS/i.test(text))return 'Обработаны не все страницы. Оставшуюся часть нужно проверить вручную.';
 if(/Embedded text was bounded|Long source text was truncated/i.test(text))return 'Часть длинного текста не вошла в запрос. Сверьте ответ с оригиналом.';
 if(/No supported answer|Question could not/i.test(text))return 'Не удалось уверенно связать ответ с заданием.';
 return /[А-Яа-яЁё]/.test(text)&&!text.trim().startsWith('{')?text:'Есть замечание к распознаванию. Сверьте текст и страницы с оригиналом.';
}
