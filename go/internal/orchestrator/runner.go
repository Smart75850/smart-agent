package orchestrator

import (
	"context"
	"sync"

	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
	"github.com/Smart75850/smart-agent-pro/go/internal/sidecar"
)

func fanOutSearch(ctx context.Context, sc *sidecar.Client, keyword string, platforms []string, limit int) (map[string][]models.Item, map[string]string) {
	results := make(map[string][]models.Item)
	errs := make(map[string]string)
	var mu sync.Mutex
	var wg sync.WaitGroup

	for _, platform := range platforms {
		wg.Add(1)
		go func(p string) {
			defer wg.Done()
			resp, err := sc.Search(ctx, p, keyword, limit)
			mu.Lock()
			defer mu.Unlock()
			if err != nil {
				errs[p] = err.Error()
				results[p] = nil
			} else {
				results[p] = resp.Items
			}
		}(platform)
	}
	wg.Wait()
	return results, errs
}

func fanOutAgents(ctx context.Context, sc *sidecar.Client, state *models.PipelineState, agents []string) map[string]any {
	reportCh := make(chan struct {
		key   string
		value any
		err   error
	}, len(agents))

	var wg sync.WaitGroup
	for _, name := range agents {
		wg.Add(1)
		go func(agentName string) {
			defer wg.Done()
			result, err := callAgent(ctx, sc, agentName, state)
			reportCh <- struct {
				key   string
				value any
				err   error
			}{agentName, result, err}
		}(name)
	}
	wg.Wait()
	close(reportCh)

	reports := make(map[string]any)
	for r := range reportCh {
		if r.err == nil && r.value != nil {
			reports[r.key] = r.value
		}
	}
	return reports
}

func callAgent(ctx context.Context, sc *sidecar.Client, name string, state *models.PipelineState) (any, error) {
	switch name {
	case "trend":
		return sc.AgentTrend(ctx, state)
	case "product":
		return sc.AgentProduct(ctx, state)
	case "video":
		return sc.AgentVideo(ctx, state)
	case "sentiment":
		return sc.AgentSentiment(ctx, state)
	case "copy":
		return sc.AgentCopy(ctx, state)
	case "remix":
		return sc.AgentRemix(ctx, state)
	case "pic":
		return sc.AgentPic(ctx, state)
	default:
		return nil, nil
	}
}
