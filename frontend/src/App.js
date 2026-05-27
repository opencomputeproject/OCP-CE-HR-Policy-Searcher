import { useEffect, useState } from 'react';
import HelpOutlinedIcon from '@mui/icons-material/HelpOutlined';
import './App.css';
import AgentPanel from './components/AgentPanel';
import LogoImage from './assets/policypulselogo.png';
import PolicyList from './components/PolicyList';
import HelpWindow from './components/HelpWindow';

const WELCOME_TUTORIAL_STORAGE_KEY = 'policy-pulse-welcome-seen';

function App() {
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isFirstRunHelpOpen, setIsFirstRunHelpOpen] = useState(false);

  const markWelcomeTutorialSeen = () => {
    try {
      window.sessionStorage.setItem(WELCOME_TUTORIAL_STORAGE_KEY, 'true');
    } catch {
      // sessionStorage can be unavailable in private or restricted browser modes.
    }
  };

  const closeWelcomeTutorial = () => {
    markWelcomeTutorialSeen();
    setIsFirstRunHelpOpen(false);
  };

  useEffect(() => {
    try {
      if (window.sessionStorage.getItem(WELCOME_TUTORIAL_STORAGE_KEY) !== 'true') {
        setIsFirstRunHelpOpen(true);
      }
    } catch {
      setIsFirstRunHelpOpen(true);
    }
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <div className="app-header-inner">
          <div className="app-brand">
            <img src={LogoImage} alt="OCP Policy Pulse" className="logo-image" />
            <div>
              <p className="app-brand-kicker">Open Compute Project</p>
              <h1>Policy Pulse</h1>
            </div>
          </div>
          <nav className="app-header-nav" aria-label="Application navigation">
            <button
              type="button"
              className="app-help-button"
              onClick={() => setIsHelpOpen(true)}
              aria-label="Open help tutorial"
              title="Help"
            >
              <HelpOutlinedIcon fontSize="small" />
              <span>Help</span>
            </button>
          </nav>
        </div>
      </header>
      <HelpWindow
        open={isFirstRunHelpOpen || isHelpOpen}
        onClose={isFirstRunHelpOpen ? closeWelcomeTutorial : () => setIsHelpOpen(false)}
      />
      <main className="App-main">
        <section className="app-stage" aria-label="Policy scanner">
          <AgentPanel />
        </section>
        <section className="app-stage" aria-label="Discovered policies">
          <PolicyList />
        </section>
      </main>
    </div>
  );
}

export default App;
