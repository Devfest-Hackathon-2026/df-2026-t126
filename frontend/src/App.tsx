import { useState } from 'react'
import { isMock } from './api'
import { DevGrid, DevPanel } from './dev/DevTools'
import { GesturePoc } from './dev/GesturePoc'
import { deriveView, useGame } from './game/useGame'
import { EntryScreen } from './screens/EntryScreen'
import { GestureScreen } from './screens/GestureScreen'
import { LobbyScreen } from './screens/LobbyScreen'
import { ProblemScreen } from './screens/ProblemScreen'
import { ResultScreen } from './screens/ResultScreen'
import { ReturnedScreen } from './screens/ReturnedScreen'
import { StartScreen } from './screens/StartScreen'
import { TextScreen } from './screens/TextScreen'
import { WaitingScreen } from './screens/WaitingScreen'
import { Wipe } from './ui/Wipe'

function Game() {
  const { state, enterRoom, camera } = useGame()
  // 入室前は、まずスタート画面を見せる。「はじめる」で名前と同意の画面へ
  const [started, setStarted] = useState(false)
  const view = deriveView(state)
  const stepIndex = state.round?.current_step_index ?? 0
  const roundId = state.roundId ?? ''
  const screenKey =
    view === 'entry' ? `entry-${started}` : view === 'text' ? `text-${stepIndex}` : view

  return (
    <>
      <Wipe viewKey={screenKey}>
        {view === 'problem' && state.problem && <ProblemScreen problem={state.problem} />}
        {view === 'loading' && <p className="screen">読み込み中です</p>}
        {view === 'entry' &&
          (started ? (
            <EntryScreen onEnter={enterRoom} onBack={() => setStarted(false)} />
          ) : (
            <StartScreen onStart={() => setStarted(true)} />
          ))}
        {view === 'lobby' && (
          <LobbyScreen
            game={state}
            cameraStatus={camera.status}
            onRetryCamera={camera.retry}
            onLeaveRoom={() => enterRoom(null)}
          />
        )}
        {view === 'waiting' && <WaitingScreen game={state} />}
        {view === 'text' && (
          <TextScreen key={`${roundId}-${stepIndex}`} roundId={roundId} stepIndex={stepIndex} />
        )}
        {view === 'gesture' && <GestureScreen key={roundId} roundId={roundId} />}
        {view === 'result' && <ResultScreen game={state} />}
        {view === 'returned' && <ReturnedScreen onNewRoom={() => enterRoom(null)} />}
      </Wipe>
      {isMock && <DevPanel roomId={state.roomId} />}
    </>
  )
}

function App() {
  const params = new URLSearchParams(location.search)
  if (params.has('poc')) return <GesturePoc />
  if (params.has('dev')) return <DevGrid />
  return <Game />
}

export default App
