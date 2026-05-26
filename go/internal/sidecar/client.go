package sidecar

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

type Client struct {
	baseURL string
	http    *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		http:    &http.Client{Timeout: 120 * time.Second},
	}
}

func (c *Client) Health(ctx context.Context) (map[string]any, error) {
	return do[map[string]any](ctx, c.http, http.MethodGet, c.baseURL+"/health", nil)
}

// ── Crawl ─────────────────────────────────────────────────

func (c *Client) Search(ctx context.Context, platform, keyword string, limit int) (models.CrawlResponse, error) {
	body := map[string]any{"platform": platform, "keyword": keyword, "limit": limit}
	return do[models.CrawlResponse](ctx, c.http, http.MethodPost, c.baseURL+"/crawl/search", body)
}

func (c *Client) Hot(ctx context.Context, platform string, limit int) (models.CrawlResponse, error) {
	body := map[string]any{"platform": platform, "limit": limit}
	return do[models.CrawlResponse](ctx, c.http, http.MethodPost, c.baseURL+"/crawl/hot", body)
}

// ── Agents ────────────────────────────────────────────────

func (c *Client) AgentTrend(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "trend", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/trend", body)
}

func (c *Client) AgentProduct(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "product", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/product", body)
}

func (c *Client) AgentVideo(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "video", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/video", body)
}

func (c *Client) AgentSentiment(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "sentiment", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/sentiment", body)
}

func (c *Client) AgentCopy(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "copy", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/copy", body)
}

func (c *Client) AgentRemix(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "remix", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/remix", body)
}

func (c *Client) AgentPic(ctx context.Context, state *models.PipelineState) (map[string]any, error) {
	body := map[string]any{"agent": "pic", "state": state}
	return do[map[string]any](ctx, c.http, http.MethodPost, c.baseURL+"/agent/pic", body)
}

// ── internal ──────────────────────────────────────────────

func do[T any](ctx context.Context, client *http.Client, method, url string, body any) (T, error) {
	var zero T
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return zero, fmt.Errorf("marshal: %w", err)
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, r)
	if err != nil {
		return zero, fmt.Errorf("request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := client.Do(req)
	if err != nil {
		return zero, fmt.Errorf("do: %w", err)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return zero, fmt.Errorf("read: %w", err)
	}
	if resp.StatusCode >= 400 {
		return zero, fmt.Errorf("status %d: %s", resp.StatusCode, string(data))
	}
	var result T
	if err := json.Unmarshal(data, &result); err != nil {
		return zero, fmt.Errorf("unmarshal: %w (body=%s)", err, string(data[:min(len(data), 200)]))
	}
	return result, nil
}
