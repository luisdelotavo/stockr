"use client";

import React, { useEffect, useState, useRef } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/firebase/config";
import ProtectedRoute from "@/components/protectedroute";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

async function getFirebaseIdToken(): Promise<string | null> {
  return new Promise((resolve) => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      unsubscribe();
      if (user) {
        const token = await user.getIdToken();
        resolve(token);
      } else {
        resolve(null);
      }
    });
  });
}

export default function AgentPage() {
  const [user, setUser] = useState<null | any>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);

      // Load existing thread ID from localStorage
      if (firebaseUser) {
        const storedThreadData = localStorage.getItem(`chat_thread_${firebaseUser.uid}`);
        if (storedThreadData) {
          try {
            const { threadId, timestamp } = JSON.parse(storedThreadData);
            // Check if thread is older than 24 hours
            const threadAge = Date.now() - timestamp;
            const oneDayInMs = 24 * 60 * 60 * 1000;

            if (threadAge < oneDayInMs) {
              setThreadId(threadId);

              // Load messages from localStorage
              const storedMessages = localStorage.getItem(`chat_messages_${firebaseUser.uid}`);
              if (storedMessages) {
                setMessages(JSON.parse(storedMessages));
              }
            } else {
              // Clear old thread data
              localStorage.removeItem(`chat_thread_${firebaseUser.uid}`);
              localStorage.removeItem(`chat_messages_${firebaseUser.uid}`);
            }
          } catch (err) {
            console.error("Error parsing stored thread data:", err);
          }
        }
      }
    });
    return () => unsubscribe();
  }, []);

  // Removed auto-scroll effect and scrollToBottom function

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && inputValue.trim()) {
      sendMessage();
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInputValue("");
    setIsLoading(true);
    setError("");

    try {
      const token = await getFirebaseIdToken();
      if (!token) throw new Error("User not authenticated");

      const endpoint = threadId
        ? `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/chat/${threadId}`
        : `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/chat`;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: userMessage.content }),
      });

      if (!response.ok) {
        // Log additional info from the response for debugging.
        const errorText = await response.text();
        console.error("Failed to send message. Status:", response.status, "Response:", errorText);
        throw new Error("Failed to send message");
      }

      const data = await response.json();

      if (data.threadId && !threadId) {
        setThreadId(data.threadId);
        localStorage.setItem(
          `chat_thread_${user.uid}`,
          JSON.stringify({
            threadId: data.threadId,
            timestamp: Date.now(),
          })
        );
      }

      const assistantMessage: Message = {
        id: Date.now().toString(),
        role: "assistant",
        content: data.answer,
        timestamp: new Date(),
      };

      const newMessages = [...updatedMessages, assistantMessage];
      setMessages(newMessages);
      localStorage.setItem(`chat_messages_${user.uid}`, JSON.stringify(newMessages));
    } catch (err: any) {
      setError(err.message || "An error occurred. Please try again.");
      console.error("Chat error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const resetChat = () => {
    setMessages([]);
    setThreadId(null);
    localStorage.removeItem(`chat_thread_${user?.uid}`);
    localStorage.removeItem(`chat_messages_${user?.uid}`);
  };

  // Determine if we should show the welcome screen or the chat interface
  const showWelcomeScreen = messages.length === 0;

  return (
    <ProtectedRoute>
      <div>
        <div className="flex flex-col items-start justify-center pl-20 h-full">
          {/* Header Section - Fixed position */}
          <header className="w-full">
            <h1 className="text-[10rem] tracking-[-0.1em] -ml-4">Agent.</h1>
            <div className="flex justify-between items-center">
              <p className="text-2xl tracking-[-0.08em] flex-1">
                The modern way to invest, providing unique insights on your personalized portfolio. Ask me a question!
              </p>
            </div>
          </header>

          {/* Content Section - This will be scrollable */}
          <div className={`w-full tracking-[-0.08em]`}>
            {/* Chat box with fixed height and scrollable content, similar to watchlist table */}
            <div className="mt-6 h-[300px] overflow-hidden border border-gray-200 rounded-lg relative">
              <div className="h-full overflow-y-auto">
                {showWelcomeScreen ? (
                  <div className="flex flex-col items-center justify-center h-full">
                    <p className="text-xl mb-4">Welcome to your personal investment agent</p>
                    <p className="text-gray-600 mb-8">
                      Ask me about your portfolio performance, investment strategies, or market trends.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 space-y-4">
                    {messages.map((message) => (
                      <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                        <div
                          className={`max-w-[75%] p-3 rounded-lg ${
                            message.role === "user" ? "bg-blue-600 text-white rounded-tr-none" : "bg-gray-100 text-gray-800 rounded-tl-none"
                          }`}
                        >
                          {message.role === "assistant" ? (
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                                ul: ({ children }) => <ul className="mb-2 last:mb-0 list-disc pl-4">{children}</ul>,
                                ol: ({ children }) => <ol className="mb-2 last:mb-0 list-decimal pl-4">{children}</ol>,
                                li: ({ children }) => <li className="mb-1">{children}</li>,
                                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                                em: ({ children }) => <em className="italic">{children}</em>,
                                code: ({ children }) => <code className="bg-gray-200 px-1 py-0.5 rounded text-sm">{children}</code>,
                                pre: ({ children }) => <pre className="bg-gray-200 p-2 rounded text-sm overflow-x-auto">{children}</pre>,
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          ) : (
                            message.content
                          )}
                        </div>
                      </div>
                    ))}
                    {isLoading && (
                      <div className="flex justify-start">
                        <div className="bg-gray-100 p-3 rounded-lg rounded-tl-none">
                          <div className="flex space-x-2">
                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse delay-75"></div>
                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse delay-150"></div>
                          </div>
                        </div>
                      </div>
                    )}
                    {error && <div className="text-red-500 text-center">{error}</div>}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              {/* Reset Chat Button - Fixed position in bottom right corner */}
              {!showWelcomeScreen && (
                <button
                  onClick={resetChat}
                  className="absolute bottom-3 right-3 w-6 h-8 flex items-center justify-center transition-all z-20"
                  title="Clear conversation"
                >
                  <span className="relative w-4 h-4 flex items-center justify-center">
                    <i className="fas fa-rotate-right text-gray-400"></i>
                  </span>
                </button>
              )}
            </div>

            {/* Input Area */}
            <div className="mt-4">
              <div className="relative">
                <input
                  type="text"
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyPress={handleKeyPress}
                  placeholder="What can I help you with today?"
                  className="w-full p-4 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={isLoading}
                />
                <button
                  onClick={sendMessage}
                  disabled={!inputValue.trim() || isLoading}
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 rounded-md bg-blue-500 text-white disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}