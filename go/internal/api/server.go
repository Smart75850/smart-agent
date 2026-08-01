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
	return authMiddleware(corsMiddleware(s.mux))
}

func (s *Server) Start(ctx context.Context) error {
	addr := s.cfg.APIHost + ":" + s.cfg.APIPort
	log.Printf("[api] 服务启动: http://%s", addr)

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

// authMiddleware — Bearer Token 鉴权，与 Python API 对齐。
// 未设置 API_TOKEN 时（本机模式）全部放行。
func authMiddleware(next http.Handler) http.Handler {
	token := os.Getenv("API_TOKEN")
	if token == "" {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		if path == "/" || path == "/health" {
			next.ServeHTTP(w, r)
			return
		}
		if r.Header.Get("Authorization") == "Bearer "+token {
			next.ServeHTTP(w, r)
			return
		}
		writeJSON(w, http.StatusUnauthorized, map[string]string{
			"error": "unauthorized", "message": "缺少或无效的 API Token",
		})
	})
}

func corsMiddleware(next http.Handler) http.Handler {
	// 收敛为明确 origins，避免 * + credentials 组合及任意站点跨源读取
	allowedOrigins := []string{
		"http://localhost:8000", "http://127.0.0.1:8000",
		"http://localhost:8001", "http://127.0.0.1:8001",
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if origin := r.Header.Get("Origin"); origin != "" {
			for _, o := range allowedOrigins {
				if origin == o {
					w.Header().Set("Access-Control-Allow-Origin", origin)
					break
				}
			}
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
	// 注意：Go 版独立编译，无法 import Python 的 constant/platform_registry.py，
	// 平台列表如有增删，需同步更新主项目注册表与本处。
	platforms := []map[string]any{
		{"id": "bilibili", "name": "B站", "hot_type": "rank", "hot_label": "排行榜", "need_login": false, "types": []string{"search", "rank", "detail", "comment", "user"}},
		{"id": "xiaohongshu", "name": "小紅書", "hot_type": "feed", "hot_label": "推薦熱門", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "douyin", "name": "抖音", "hot_type": "keyword", "hot_label": "熱搜關鍵詞", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "zhihu", "name": "知乎", "hot_type": "question", "hot_label": "熱榜問題", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "kuaishou", "name": "快手", "hot_type": "video", "hot_label": "熱播視頻", "need_login": false, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "weibo", "name": "微博", "hot_type": "topic", "hot_label": "熱搜話題", "need_login": true, "types": []string{"search", "hot", "detail", "comment", "user"}},
		{"id": "tieba", "name": "貼吧", "hot_type": "post", "hot_label": "熱門帖子", "need_login": false, "types": []string{"search", "hot", "detail", "comment", "user"}},
	}
	writeJSON(w, http.StatusOK, map[string]any{"platforms": platforms})
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	// 明确 501：Go 版不提供 WebSocket，实时日志请用 Python API（8000）
	writeError(w, http.StatusNotImplemented, "WebSocket not available in Go server, use Python server (port 8000) for real-time logs")
}
