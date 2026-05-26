package models

// Item 标准化内容条目。
type Item struct {
	Title      string `json:"title"`
	Author     string `json:"author"`
	Plays      string `json:"plays"`
	Likes      string `json:"likes"`
	Link       string `json:"link"`
	Platform   string `json:"platform"`
	PlatformID string `json:"platform_id"`
	CoverURL   string `json:"cover_url,omitempty"`
}

// PipelineState 管道状态，对应 Python PipelineState。
type PipelineState struct {
	Keyword         string   `json:"keyword"`
	Limit           int      `json:"limit"`
	Platforms       []string `json:"platforms"`
	PipelineMode    string   `json:"pipeline_mode"` // "simple" | "full"
	SearchResults   map[string][]Item `json:"search_results,omitempty"`
	MergedItems     []Item            `json:"merged_items,omitempty"`
	ScoredItems     []Item            `json:"scored_items,omitempty"`
	FilteredItems   []Item            `json:"filtered_items,omitempty"`
	Errors          map[string]string `json:"errors,omitempty"`

	// Agent outputs
	TrendReports     map[string]any `json:"trend_reports,omitempty"`
	ProductReport    any            `json:"product_report,omitempty"`
	VideoReport      any            `json:"video_report,omitempty"`
	SentimentReport  any            `json:"sentiment_report,omitempty"`
	CopyReport       any            `json:"copy_report,omitempty"`
	RemixReport      any            `json:"remix_report,omitempty"`
	VisualReport     any            `json:"visual_report,omitempty"`
}

// CrawlResponse sidecar 爬取响应。
type CrawlResponse struct {
	Items []Item `json:"items"`
	Error string `json:"error"`
}

// PipelineResult 管道最终输出。
type PipelineResult struct {
	Keyword      string           `json:"keyword"`
	Platforms    []string         `json:"platforms"`
	TotalItems   int              `json:"total_items"`
	PipelineMode string           `json:"pipeline_mode"`
	Items        []Item           `json:"items"`
	Reports      map[string]any   `json:"reports,omitempty"`
	Errors       map[string]string `json:"errors,omitempty"`
}
