package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log"
	"net/http"
	"time"

	"github.com/Smart75850/smart-agent-pro/go/internal/orchestrator"
	"github.com/Smart75850/smart-agent-pro/go/pkg/models"
)

type pipelineRequest struct {
	Keyword      string   `json:"keyword"`
	Platforms    []string `json:"platforms"`
	Limit        int      `json:"limit"`
	PipelineMode string   `json:"pipeline_mode"` // "simple" | "full"
}

func (s *Server) handlePipelineCreate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}
	var req pipelineRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if req.Keyword == "" {
		writeError(w, http.StatusBadRequest, "keyword is required")
		return
	}
	if req.PipelineMode == "" {
		req.PipelineMode = "full"
	}
	if req.Limit <= 0 {
		req.Limit = 10
	}

	taskID := newTaskID()
	s.store.Set(taskID, &TaskStatus{
		ID:        taskID,
		Status:    "pending",
		CreatedAt: time.Now(),
	})

	go s.runPipeline(taskID, req)

	writeJSON(w, http.StatusAccepted, map[string]string{"task_id": taskID})
}

func (s *Server) handlePipelineGet(w http.ResponseWriter, r *http.Request) {
	taskID := r.PathValue("task_id")
	if taskID == "" {
		writeError(w, http.StatusBadRequest, "task_id required")
		return
	}
	task := s.store.Get(taskID)
	if task == nil {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	writeJSON(w, http.StatusOK, task)
}

func (s *Server) runPipeline(taskID string, req pipelineRequest) {
	s.store.Set(taskID, &TaskStatus{
		ID:        taskID,
		Status:    "running",
		CreatedAt: time.Now(),
	})

	state := &models.PipelineState{
		Keyword:      req.Keyword,
		Platforms:    req.Platforms,
		Limit:        req.Limit,
		PipelineMode: req.PipelineMode,
	}

	graph := orchestrator.NewGraph(req.PipelineMode)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	result, err := graph.Run(ctx, state)
	if err != nil {
		log.Printf("[pipeline] task=%s failed: %v", taskID, err)
		s.store.Set(taskID, &TaskStatus{
			ID:        taskID,
			Status:    "failed",
			CreatedAt: time.Now(),
			Error:     err.Error(),
		})
		return
	}

	log.Printf("[pipeline] task=%s completed: %d items", taskID, result.TotalItems)
	s.store.Set(taskID, &TaskStatus{
		ID:        taskID,
		Status:    "completed",
		CreatedAt: time.Now(),
		Result:    result,
	})
}

func newTaskID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)[:12]
}
