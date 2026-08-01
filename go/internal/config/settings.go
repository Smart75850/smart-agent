package config

import "os"

type Settings struct {
	SidecarURL string
	APIPort    string
	APIHost    string
}

func Load() *Settings {
	s := &Settings{
		SidecarURL: env("SIDECAR_URL", "http://127.0.0.1:18500"),
		// 默认 8001，避免与 Python API (8000) 端口冲突
		APIPort: env("API_PORT", "8001"),
		APIHost: env("API_HOST", "127.0.0.1"),
	}
	return s
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
