import {useState} from 'react';
import ExplainTerms from './ExplainTerms';

export default function KnowledgeFilterUpdate({language,excerpt}:{language:'en'|'ko';excerpt?:string}) {
 const [step,setStep]=useState(0);
 const t=(en:string,ko:string)=>language==='ko'?ko:en;
 let savedQuery='';
 try {const data=JSON.parse(excerpt||'{}');savedQuery=String(data.first_search_arguments?.queries||'').split(',')[0].trim();} catch {/* A missing local record never becomes an invented example. */}
 const stages=[
  {name:t('Available choices','선택지 확인'),who:t('Program','프로그램'),title:t('First, check how the documents are classified','먼저, 자료가 어떤 분류로 정리되어 있는지 확인합니다'),
   body:t('Think of a library: before choosing a shelf, check which shelves actually exist. The program reads category labels from the knowledge documents available to this run and puts those choices in the search tool description given to the AI.','도서관에서 책을 찾는다고 생각해 보세요. 먼저 어떤 서가가 있는지 확인해야 합니다. 프로그램은 이번 실행이 접근할 수 있는 지식 문서에 붙은 분류를 읽고, 그 선택지를 AI에게 전달할 검색 도구 설명에 넣습니다.'),
   example:t('A topic mentioned inside a document does not automatically become a category. HIV can appear in a document even when there is no HIV category.','문서에 어떤 주제가 나온다고 그 이름의 분류도 생기는 것은 아닙니다. HIV 분류가 없어도 문서에는 HIV 관련 내용이 있을 수 있습니다.'),
   outcome:t('The AI receives real category choices, not permission to invent new ones.','AI는 실제로 존재하는 분류 선택지를 받습니다. 분류 이름을 새로 만드는 단계가 아닙니다.')},
  {name:t('AI request','AI의 요청'),who:t('AI','AI'),title:t('The AI chooses search words and, optionally, a category','AI가 검색어를 정하고, 필요하면 분류를 선택합니다'),
   body:t('The search words describe what the AI wants to find. A category restricts where the program looks. These are separate decisions. Search words can vary with the assignment and information received so far; the category must come from the supplied choices.','검색어는 “무엇에 관한 자료를 찾을까?”이고, 분류 조건은 “어느 범위의 자료에서 찾을까?”입니다. 둘은 서로 다른 선택입니다. AI가 받은 과제와 지금까지 얻은 정보에 따라 검색어는 달라질 수 있지만, 분류는 제공된 선택지에서 골라야 합니다.'),
   example:savedQuery?t(`The saved run used the search words “${savedQuery}”. To illustrate the current input, keep those words in queries and omit filters when no extra category restriction is intended. This is not a new search result.`,`저장된 실행에서 사용한 검색어는 “${savedQuery}”입니다. 현재 입력 방식으로 설명하면 이 말을 검색어에 넣고, 추가 분류 제한이 필요 없을 때는 분류 조건을 생략합니다. 새로 검색한 결과를 보여주는 것은 아닙니다.`):t('“Find HIV-related documents” is a topic request. “Only search the psychiatric category” is an additional scope restriction. Omitting that restriction still respects the run’s access limits.','“HIV 관련 문서를 찾아줘”는 검색 주제입니다. “정신질환 분류에서만 찾아줘”는 추가 범위 조건입니다. 추가 조건을 생략해도 실행에 지정된 접근 제한은 유지됩니다.'),
   outcome:t('The AI sends a tool request containing the search words and selected restrictions. It has not read a document yet through this request.','AI는 검색어와 선택한 조건을 담은 도구 요청을 보냅니다. 이 요청을 만든 것만으로 문서를 읽은 것은 아닙니다.')},
  {name:t('Validation','조건 검사'),who:t('Program','프로그램'),title:t('The program checks the request before searching','검색하기 전에 프로그램이 요청을 검사합니다'),
   body:t('The tool checks whether the category is available and whether the request stays within the run’s permitted scope. Conditions are checked again against the corpus. The AI cannot bypass that check merely by writing a different value.','도구는 선택한 분류가 실제 선택지에 있는지, 이번 실행에서 허용된 범위 안인지 확인합니다. 실제 자료를 기준으로 조건을 다시 검증하므로 AI가 다른 값을 적었다고 그대로 검색하지 않습니다.'),
   example:t('If hiv is not a category, a request to use it as a category is blocked. The AI must correct the request using valid choices. The program does not secretly replace it with psychiatric or remove the condition.','hiv라는 분류가 없는데 그 분류로 검색하라고 요청하면 차단합니다. AI가 유효한 선택지에 맞춰 요청을 고쳐야 합니다. 프로그램이 몰래 psychiatric으로 바꾸거나 조건을 삭제하지 않습니다.'),
   outcome:t('A valid request proceeds. A rejected request returns validation feedback instead of document candidates.','유효한 요청은 검색으로 넘어갑니다. 거절된 요청에는 문서 후보 대신 검증 오류가 반환됩니다.')},
  {name:t('Find and rank','검색과 정렬'),who:t('Program','프로그램'),title:t('The program compares search words with document labels','프로그램이 검색어와 문서 소개 정보를 비교합니다'),
   body:t('At this stage the program checks the title, tags, description and journal field. It does not search the document body. Matching words add a score: title matches carry more weight, and words found in fewer documents carry more weight. Candidates are sorted by that score.','이 단계에서는 문서의 제목, 태그, 설명, 저널 항목을 확인합니다. 문서 본문 전체를 검색하지는 않습니다. 검색어와 일치하는 단어가 있으면 점수를 더합니다. 제목의 일치와 여러 문서에 흔하지 않은 단어의 일치에 더 큰 비중을 두고, 점수가 높은 후보부터 정렬합니다.'),
   example:t('This is like checking a library catalog before opening the books. A high search score means a stronger match to the search words; it does not mean the medical claim is true or the eventual prediction model will be accurate.','책을 펼치기 전에 도서관의 책 소개 목록을 찾아보는 과정과 같습니다. 검색 점수가 높다는 것은 검색어와 잘 맞는다는 뜻입니다. 의학적 주장이 참이거나 나중에 학습할 예측 모델의 성능이 높다는 뜻은 아닙니다.'),
   outcome:t('Ranked candidates are produced by a word-matching calculation. The AI does not assign these search scores.','단어 일치 계산으로 문서 후보의 순서가 정해집니다. 이 검색 점수를 AI가 직접 매기는 것은 아닙니다.')},
  {name:t('Return to AI','AI에게 반환'),who:t('Program → AI','프로그램 → AI'),title:t('The AI receives a reading list, then chooses what to open','AI는 읽을 후보 목록을 받고, 열어 볼 문서를 선택합니다'),
   body:t('The response contains document identifiers, titles, metadata and search scores. It also records the requested and applied filters. The result limit controls how many top candidates are shown per search wording; it is not the number of all relevant documents.','응답에는 문서 식별자, 제목, 소개 정보와 검색 점수가 들어갑니다. 요청한 조건과 실제 적용한 조건도 기록됩니다. 결과 개수 제한은 검색어별로 상위 후보를 몇 개 보여줄지 정하는 값이며, 관련 문서 전체의 개수와 같지는 않습니다.'),
   example:t('The identifier is the address used to open a document in the next Read step. The AI may choose a candidate to read or search again. No matching candidates does not establish that the scientific relationship is absent.','문서 식별자는 다음 “문서 읽기” 단계에서 해당 문서를 여는 주소입니다. AI는 후보를 골라 읽거나 검색어를 바꿔 다시 찾을 수 있습니다. 후보가 없다고 과학적 관계도 없다고 결론 내릴 수는 없습니다.'),
   outcome:t('Search ends with document candidates. Reading their contents and proposing a hypothesis are later steps.','검색 단계에서 얻는 것은 문서 후보입니다. 본문을 읽고 가설을 만드는 일은 다음 단계에서 이어집니다.')},
 ];
 const current=stages[step];
 return <section className="hyp-filter-update" aria-label={t('Current document search','현재 문서 검색')}>
  <h3 id="hyp-current-search">{t('How does the AI find documents to read?','AI는 읽을 문서를 어떻게 찾나요?')}</h3>
  <p>{t('Follow five small steps. The AI chooses what to ask for; code checks the request and finds matching documents.','작은 과정 다섯 개로 나눠 살펴보세요. AI는 무엇을 찾을지 정하고, 코드는 요청을 검사한 뒤 맞는 문서를 찾습니다.')}</p>
  <nav className="hyp-search-steps" aria-label={t('Search process','검색 세부 과정')}>{stages.map((item,i)=><button key={i} aria-current={i===step?'step':undefined} onClick={()=>setStep(i)}>{i+1}. {item.name}</button>)}</nav>
  <div className="hyp-search-explanation" aria-live="polite" aria-atomic="true">
   <p className="eyebrow">{step+1} / 5 · {current.who}</p><h4>{current.title}</h4>
   <p>{current.body}</p><div className="hyp-search-example"><strong>{t('To make this concrete','쉽게 이해하면')}</strong><p>{current.example}</p></div>
   <p><strong>{t('What passes to the next step: ','다음으로 전달되는 것: ')}</strong>{current.outcome}</p>
  </div>
  <div className="hyp-search-nav"><button disabled={step===0} onClick={()=>setStep(s=>s-1)}>{t('← Previous search step','← 이전 검색 과정')}</button><span>{step+1} / 5</span><button disabled={step===4} onClick={()=>setStep(s=>s+1)}>{t('Next search step →','다음 검색 과정 →')}</button></div>
  {step===4&&<p>{t('You can now use the main Next button below to continue to Read.','이제 아래쪽의 전체 단계 “다음” 버튼으로 “문서 읽기”에 넘어갈 수 있습니다.')}</p>}
  <details className="hyp-extra"><summary>{t('Technical names and scope of this explanation','기술 이름과 이 설명의 범위')}</summary><ExplainTerms language={language} text={t('okf_list_domains lists available knowledge categories. okf_search validates structured filters and searches metadata. okf_read opens a selected document. This is the current implementation, not a new completed LLM experiment. Historical records remain separately below.','okf_list_domains는 사용 가능한 지식 분류를 알려줍니다. okf_search는 구조화된 조건을 검증하고 문서 소개 정보를 검색합니다. okf_read는 선택한 문서를 엽니다. 현재 코드의 처리 방식을 설명하는 것이며 새 LLM 실험 완료 결과는 아닙니다. 과거 기록은 아래에 별도로 보존합니다.')}/></details>
 </section>;
}
