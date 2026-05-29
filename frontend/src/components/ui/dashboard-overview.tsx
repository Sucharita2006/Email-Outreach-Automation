import React from 'react';
import { motion } from 'framer-motion';
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowDown, ArrowUp, Minus, Users, DollarSign, Clock, AlertCircle } from 'lucide-react';

type IconType = React.ElementType | React.FunctionComponent<React.SVGProps<SVGSVGElement>>;
export type TrendType = 'up' | 'down' | 'neutral';

export interface DashboardMetricCardProps {
  value: string | number;
  title: string;
  icon?: IconType;
  iconColor?: string;
  trendChange?: string | number;
  trendType?: TrendType;
  className?: string;
}

export const DashboardMetricCard: React.FC<DashboardMetricCardProps> = ({
  value,
  title,
  icon: IconComponent,
  iconColor = '#6366f1',
  trendChange,
  trendType = 'neutral',
  className,
}) => {
  const TrendIcon = trendType === 'up' ? ArrowUp : trendType === 'down' ? ArrowDown : Minus;
  const trendColorClass =
    trendType === 'up'
      ? "text-green-600 dark:text-green-400"
      : trendType === 'down'
      ? "text-red-600 dark:text-red-400"
      : "text-muted-foreground";

  return (
    <motion.div
      whileHover={{ y: -4, boxShadow: `0 10px 25px -5px ${iconColor}33` }}
      transition={{ type: "spring", stiffness: 400, damping: 20 }}
      className={cn("cursor-pointer rounded-lg", className)}
    >
      <Card className="h-full transition-colors duration-200 overflow-hidden" style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}>
        {/* Colored top accent strip */}
        <div style={{ height: 3, background: `linear-gradient(90deg, ${iconColor}, ${iconColor}66)` }} />
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2" style={{ padding: '16px' }}>
          <CardTitle className="text-sm font-medium text-muted-foreground" style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            {title}
          </CardTitle>
          {IconComponent && (
            <div style={{ 
              width: 32, height: 32, borderRadius: 8, 
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: `${iconColor}18`
            }}>
              <IconComponent className="h-4 w-4" aria-hidden="true" style={{ color: iconColor }} />
            </div>
          )}
        </CardHeader>
        <CardContent style={{ padding: '0 16px 16px' }}>
          <div className="text-2xl font-bold text-foreground mb-2" style={{ 
            fontSize: '2rem', 
            fontWeight: 800, 
            color: 'var(--text-primary)'
          }}>
            {value}
          </div>
          {trendChange && (
            <p className={cn("flex items-center text-xs font-medium", trendColorClass)}>
              <TrendIcon className="h-3 w-3 mr-1" aria-hidden="true" />
              {trendChange}
            </p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
};
