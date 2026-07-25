import {
  ZoomIn, ZoomOut, Maximize2, Minimize2, RotateCcw, Crosshair,
  Pause, Play, Lock, Unlock, Compass,
} from "lucide-react";

type GraphToolbarProps = {
  isFullscreen: boolean;
  isFrozen: boolean;
  isPaused: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitGraph: () => void;
  onResetLayout: () => void;
  onCenterSelection: () => void;
  onToggleFullscreen: () => void;
  onToggleFreeze: () => void;
  onTogglePause: () => void;
};

function ToolBtn({
  icon: Icon,
  label,
  onClick,
  active = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`flex h-8 w-8 items-center justify-center rounded-lg transition-all hover:bg-primary/20 hover:text-primary ${
        active ? "bg-primary/20 text-primary" : "text-muted-foreground"
      }`}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

export function GraphToolbar({
  isFullscreen,
  isFrozen,
  isPaused,
  onZoomIn,
  onZoomOut,
  onFitGraph,
  onResetLayout,
  onCenterSelection,
  onToggleFullscreen,
  onToggleFreeze,
  onTogglePause,
}: GraphToolbarProps) {
  return (
    <div
      className="absolute right-3 top-3 z-20 flex flex-col gap-1 rounded-xl p-1.5 shadow-xl animate-slide-in"
      style={{
        backgroundColor: "var(--overlay-bg)",
        border: "1px solid var(--overlay-border)",
        backdropFilter: "blur(12px)",
      }}
    >
      <ToolBtn icon={ZoomIn} label="Zoom In" onClick={onZoomIn} />
      <ToolBtn icon={ZoomOut} label="Zoom Out" onClick={onZoomOut} />
      <ToolBtn icon={Compass} label="Fit Graph" onClick={onFitGraph} />
      <ToolBtn icon={Crosshair} label="Center Selection" onClick={onCenterSelection} />

      <div className="mx-1 my-0.5 h-px bg-border/40" />

      <ToolBtn icon={isPaused ? Play : Pause} label={isPaused ? "Resume Simulation" : "Pause Simulation"} onClick={onTogglePause} active={isPaused} />
      <ToolBtn icon={isFrozen ? Unlock : Lock} label={isFrozen ? "Unfreeze Layout" : "Freeze Layout"} onClick={onToggleFreeze} active={isFrozen} />
      <ToolBtn icon={RotateCcw} label="Reset Layout" onClick={onResetLayout} />

      <div className="mx-1 my-0.5 h-px bg-border/40" />

      <ToolBtn
        icon={isFullscreen ? Minimize2 : Maximize2}
        label={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        onClick={onToggleFullscreen}
        active={isFullscreen}
      />
    </div>
  );
}
