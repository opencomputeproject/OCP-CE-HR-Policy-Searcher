import { useCallback, useEffect, useState } from 'react';
import HelpOutlinedIcon from '@mui/icons-material/HelpOutlined';
import './App.css';
import AgentPanel from './components/AgentPanel';
import AskPolicyBox from './components/AskPolicyBox';
import LogoImage from './assets/ocp-logo.svg';
import LeadsInbox from './components/LeadsInbox';
import PolicyList from './components/PolicyList';
import ReviewInbox from './components/ReviewInbox';
import HelpWindow from './components/HelpWindow';
import { apiUrl } from './config/api';
import { getAdminToken } from './utils/adminAuth';

const WELCOME_TUTORIAL_STORAGE_KEY = 'policy-pulse-welcome-seen';

function App() {
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isFirstRunHelpOpen, setIsFirstRunHelpOpen] = useState(false);
  const [adminRequired, setAdminRequired] = useState(false);
  const [hasAdminToken, setHasAdminToken] = useState(Boolean(getAdminToken()));

  const refreshAdminTokenStatus = useCallback(() => {
    setHasAdminToken(Boolean(getAdminToken()));
  }, []);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch(apiUrl('/health'));
        if (!response.ok) throw new Error();
        const data = await response.json();
        setAdminRequired(Boolean(data.admin_required));
      } catch {
        setAdminRequired(false);
      }
    };

    fetchHealth();
  }, []);

  const markWelcomeTutorialSeen = () => {
    try {
      window.localStorage.setItem(WELCOME_TUTORIAL_STORAGE_KEY, 'true');
    } catch {
      // localStorage can be unavailable in private or restricted browser modes.
    }
  };

  const closeWelcomeTutorial = () => {
    markWelcomeTutorialSeen();
    setIsFirstRunHelpOpen(false);
  };

  useEffect(() => {
    try {
      if (window.localStorage.getItem(WELCOME_TUTORIAL_STORAGE_KEY) !== 'true') {
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
            <img src={LogoImage} alt="Open Compute Project" className="logo-image" />
            <div className="app-brand-title">
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
          <AgentPanel
            adminRequired={adminRequired}
            hasAdminToken={hasAdminToken}
            onAdminTokenChange={refreshAdminTokenStatus}
          />
        </section>
        <section className="app-stage" aria-label="Discovered policies">
          <ReviewInbox isAdmin={!adminRequired || hasAdminToken} />
          <AskPolicyBox />
          <LeadsInbox adminRequired={adminRequired} hasAdminToken={hasAdminToken} />
          <PolicyList />
        </section>
      </main>
    </div>
  );
}

export default App;
