package config

import "os"

type Settings struct {
	SidecarURL string
	APIPort    string
}

func Load() *Settings {
	s := &Settings{
		SidecarURL: env("SIDECAR_URL", "http://127.0.0.1:18500"),
		APIPort:    env("API_PORT", "8000"),
	}
	return s
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
