package api

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/Smart75850/smart-agent-pro/go/internal/config"
)

type Server struct {
	cfg   *config.Settings
	mux   *http.ServeMux
	store *TaskStore
}

type TaskStatus struct {
	ID        string    `json:"id"`
	Status    string    `json:"status"` // pending / running / completed / failed
	CreatedAt time.Time `json:"created_at"`
	Result    any       `json:"result,omitempty"`
	Error     string    `json:"error,omitempty"`
}

type TaskStore struct {
	mu    sync.RWMutex
	tasks map[string]*TaskStatus
}

func NewTaskStore() *TaskStore {
	return &TaskStore{tasks: make(map[string]*TaskStatus)}
}

func (ts *TaskStore) Get(id string) *TaskStatus {
	ts.mu.RLock()
	defer ts.mu.RUnlock()
	return ts.tasks[id]
}

func (ts *TaskStore) Set(id string, t *TaskStatus) {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	ts.tasks[id] = t
}

func NewServer(cfg *config.Settings) *Server {
	s := &Server{
		cfg:   cfg,
		mux:   http.NewServeMux(),
		store: NewTaskStore(),
	}
	s.registerRoutes()
	return s
}

func (s *Server) Handler() http.Handler {
	return corsMiddleware(s.mux)
}

func (s *Server) Start(ctx context.Context) error {
	addr := ":" + s.cfg.APIPort
	log.Printf("[api] 服务启动: http://localhost%s", addr)

	srv := &http.Server{
		Addr:    addr,
		Handler: s.Handler(),
	}
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		srv.Shutdown(shutdownCtx)
	}()
	return srv.ListenAndServe()
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func (s *Server) registerRoutes() {
	s.mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	s.mux.HandleFunc("POST /api/pipeline", s.handlePipelineCreate)
	s.mux.HandleFunc("GET /api/pipeline/{task_id}", s.handlePipelineGet)
	s.mux.HandleFunc("POST /api/crawl", s.handleCrawl)
	s.mux.HandleFunc("GET /api/data/{platform}", s.handleDataPlatform)
	s.mux.HandleFunc("GET /api/data", s.handleDataList)
	s.mux.HandleFunc("GET /api/platforms", s.handlePlatforms)
	s.mux.HandleFunc("GET /", s.handleWebUI)
	s.mux.HandleFunc("GET /api/ws", s.handleWebSocket)
}

func decodeJSON(r *http.Request, v any) error {
	defer r.Body.Close()
	return json.NewDecoder(r.Body).Decode(v)
}

func (s *Server) handleWebUI(w http.ResponseWriter, r *http.Request) {
	webuiPath := filepath.Join("api", "webui", "index.html")
	data, err := os.ReadFile(webuiPath)
	if err != nil {
		writeError(w, http.StatusNotFound, "WebUI not found — please run from project root")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write(data)
}

func (s *Server) handlePlatforms(w http.ResponseWriter, r *http.Request) {
	platforms := []map[string]any{
		{"id": "bilibili", "name": "B站", "need_login": false, "types": []string{"search", "rank", "detail", "comment", "user"}},
		{"id": "xiaohongshu", "name": "小紅書", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "douyin", "name": "抖音", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "zhihu", "name": "知乎", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "kuaishou", "name": "快手", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "weibo", "name": "微博", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "tieba", "name": "貼吧", "need_login": false, "types": []string{"search", "hot", "detail", "comment", "user"}},
	}
	writeJSON(w, http.StatusOK, map[string]any{"platforms": platforms})
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"message": "WebSocket not available in Go server, use Python server for real-time logs"})
}
