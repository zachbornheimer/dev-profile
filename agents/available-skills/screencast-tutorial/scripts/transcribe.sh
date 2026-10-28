#!/usr/bin/env bash
# Transcribe a video locally with whisper.cpp + Silero VAD.
# Usage: transcribe.sh <video> <workdir> [glossary prompt]
# Writes <workdir>/audio.wav, transcript.{srt,vtt,txt,json}, whisper.log.
set -euo pipefail

video=${1:?usage: transcribe.sh <video> <workdir> [glossary]}
workdir=${2:?usage: transcribe.sh <video> <workdir> [glossary]}
glossary=${3:-}
cache="$HOME/.cache/whisper.cpp"
hf="https://huggingface.co"

for bin in ffmpeg whisper-cli curl; do
	command -v "$bin" >/dev/null || {
		echo "missing: $bin (brew install ffmpeg whisper-cpp)" >&2
		exit 1
	}
done
mkdir -p "$workdir" "$cache"

# Model: explicit > Superwhisper's downloads > cache > download large-v3-turbo.
model=${WHISPER_MODEL:-}
if [[ -z $model ]]; then
	for candidate in \
		"$HOME/Library/Application Support/superwhisper/ggml-large-v3-turbo.bin" \
		"$cache/ggml-large-v3-turbo.bin" \
		"$HOME/Library/Application Support/superwhisper/ggml-medium.bin" \
		"$cache/ggml-medium.en.bin" \
		"$HOME/Library/Application Support/superwhisper/ggml-small.bin"; do
		[[ -s $candidate ]] && {
			model=$candidate
			break
		}
	done
fi
if [[ -z $model ]]; then
	model="$cache/ggml-large-v3-turbo.bin"
	echo "downloading $model (1.6 GB)" >&2
	curl -fL --progress-bar -o "$model.part" "$hf/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
	mv "$model.part" "$model"
fi

vad="$cache/ggml-silero-v5.1.2.bin"
[[ -s $vad ]] || curl -fsSL -o "$vad" "$hf/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin"

ffmpeg -nostdin -y -loglevel error -i "$video" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$workdir/audio.wav"

echo "model: $model" >&2
args=(-m "$model" -f "$workdir/audio.wav" -l en -t "$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || echo 8)"
	--vad -vm "$vad" -osrt -ovtt -otxt -oj -of "$workdir/transcript")
[[ -n $glossary ]] && args+=(--prompt "$glossary")
whisper-cli "${args[@]}" >"$workdir/whisper.log" 2>&1 || {
	tail -20 "$workdir/whisper.log" >&2
	exit 1
}

segments=$(grep -c -- '-->' "$workdir/transcript.srt")
last=$(grep -- '-->' "$workdir/transcript.srt" | tail -1 | cut -c18-29)
echo "ok: $segments segments, last ends $last → $workdir/transcript.{srt,vtt,txt,json}"
