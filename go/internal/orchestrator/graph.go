package orchestrator

import (
	"context"
	"crypto/sha256"
	"fmt"
	"log"

	"github.com/Smart75850/smart-agent-pro/go/internal/crawler"
	"github.com/Smart75850/smart-agent-pro/go/internal/sidecar"
	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

type Graph struct {
	mode string
}

func NewGraph(mode string) *Graph {
	if mode == "" {
		mode = "simple"
	}
	return &Graph{mode: mode}
}

func (g *Graph) Run(ctx context.Context, state *models.PipelineState) (*models.PipelineResult, error) {
	sc := sidecar.NewClient("http://127.0.0.1:18500")

	platforms := state.Platforms
	if len(platforms) == 0 {
		platforms = []string{"bilibili"}
	}
	if state.Limit <= 0 {
		state.Limit = 10
	}

	taskID := makeTaskID(state.Keyword, platforms)
	log.Printf("[pipeline] task=%s mode=%s keyword=%q platforms=%v", taskID, g.mode, state.Keyword, platforms)

	// Stage 1: 多平台并行搜索
	log.Println("[pipeline] Stage 1: 并行搜索...")
	searchResults, searchErrs := fanOutSearch(ctx, sc, state.Keyword, platforms, state.Limit)
	state.SearchResults = searchResults
	if state.Errors == nil {
		state.Errors = make(map[string]string)
	}
	for p, e := range searchErrs {
		state.Errors[p] = e
	}

	// Stage 2: 合并 + 去重
	log.Println("[pipeline] Stage 2: 合并去重...")
	merged := crawler.MergeAndDedup(searchResults)
	state.MergedItems = merged
	log.Printf("[pipeline] 共 %d 条 (去重后)", len(merged))

	if g.mode == "simple" {
		return &models.PipelineResult{
			Keyword:      state.Keyword,
			Platforms:    platforms,
			TotalItems:   len(merged),
			PipelineMode: "simple",
			Items:        merged,
			Errors:       state.Errors,
		}, nil
	}

	// Stage 3: TrendScout (串行前置 — 后续 agent 依赖 trend_reports)
	log.Println("[pipeline] Stage 3: TrendScout...")
	trendResult, _ := sc.AgentTrend(ctx, state)
	if trendResult != nil {
		state.TrendReports = map[string]any{"__combined__": trendResult}
	}

	// Stage 4: Level 1 并行 Agents (product + video + sentiment)
	log.Println("[pipeline] Stage 4: Level 1 agents (product/video/sentiment)...")
	level1Results := fanOutAgents(ctx, sc, state, []string{"product", "video", "sentiment"})
	for k, v := range level1Results {
		switch k {
		case "product":
			state.ProductReport = v
		case "video":
			state.VideoReport = v
		case "sentiment":
			state.SentimentReport = v
		}
	}

	// Stage 5: Level 2 并行 Agents (copy + remix + pic)
	log.Println("[pipeline] Stage 5: Level 2 agents (copy/remix/pic)...")
	level2Results := fanOutAgents(ctx, sc, state, []string{"copy", "remix", "pic"})
	for k, v := range level2Results {
		switch k {
		case "copy":
			state.CopyReport = v
		case "remix":
			state.RemixReport = v
		case "pic":
			state.VisualReport = v
		}
	}

	// Stage 6: 组装结果
	result := &models.PipelineResult{
		Keyword:      state.Keyword,
		Platforms:    platforms,
		TotalItems:   len(merged),
		PipelineMode: "full",
		Items:        merged,
		Reports: map[string]any{
			"trend":     state.TrendReports,
			"product":   state.ProductReport,
			"video":     state.VideoReport,
			"sentiment": state.SentimentReport,
			"copy":      state.CopyReport,
			"remix":     state.RemixReport,
			"pic":       state.VisualReport,
		},
		Errors: state.Errors,
	}

	log.Printf("[pipeline] 任务 %s 完成", taskID)
	return result, nil
}

func makeTaskID(keyword string, platforms []string) string {
	h := sha256.New()
	h.Write([]byte(fmt.Sprintf("%s|%v", keyword, platforms)))
	return fmt.Sprintf("%x", h.Sum(nil))[:8]
}
