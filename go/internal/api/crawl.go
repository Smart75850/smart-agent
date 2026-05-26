package api

import (
	"context"
	"net/http"
	"time"

	"github.com/Smart75850/smart-agent-pro/go/internal/sidecar"
	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

type crawlRequest struct {
	Platform string `json:"platform"`
	Keyword  string `json:"keyword"`
	Type     string `json:"type"` // "search" | "hot"
	Limit    int    `json:"limit"`
}

func (s *Server) handleCrawl(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}
	var req crawlRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if req.Limit <= 0 {
		req.Limit = 10
	}
	if req.Type == "" {
		req.Type = "search"
	}

	sc := sidecar.NewClient("http://127.0.0.1:18500")
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	var resp models.CrawlResponse
	var err error
	switch req.Type {
	case "hot":
		resp, err = sc.Hot(ctx, req.Platform, req.Limit)
	default:
		resp, err = sc.Search(ctx, req.Platform, req.Keyword, req.Limit)
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}
